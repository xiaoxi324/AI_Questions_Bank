import os
import sys
from docx import Document
from docx.document import Document as _Document
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph

# 路径与上下文修复
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from backend.tools.tools_sql_connect import db
from backend.tools.global_context import log_queue_ctx


def emit(msg):
    """日志推送"""
    print(msg)
    q = log_queue_ctx.get()
    if q: q.put(f"LOG: {msg}")


class WordParser:
    def _iter_block_items(self, parent):
        if isinstance(parent, _Document):
            parent_elm = parent.element.body
        elif isinstance(parent, _Cell):
            parent_elm = parent._tc
        else:
            raise ValueError("Unsupported parent type")
        for child in parent_elm.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield Table(child, parent)

    def _table_to_markdown(self, table: Table) -> str:
        rows_data = []
        for row in table.rows:
            cell_texts = [cell.text.strip().replace("\n", "<br>") for cell in row.cells]
            rows_data.append(f"| {' | '.join(cell_texts)} |")
        if not rows_data: return ""
        header = rows_data[0]
        separator = "|" + "|".join(["---"] * len(table.rows[0].cells)) + "|"
        body = "\n".join(rows_data[1:])
        return f"\n{header}\n{separator}\n{body}\n"

    def parse_docx(self, file_path: str) -> list:
        if not os.path.exists(file_path): return []
        document = Document(file_path)
        chunks = []
        for block in self._iter_block_items(document):
            if isinstance(block, Paragraph):
                lines = block.text.split('\n')
                for line in lines:
                    if line.strip(): chunks.append(line.strip())
            elif isinstance(block, Table):
                md_table = self._table_to_markdown(block)
                if md_table.strip():
                    chunks.append(f"【表格数据】\n{md_table}")
        return chunks


def execute_split_task(book_id: int):
    emit(f"🔪 [切分] 开始处理 BookID={book_id}...")

    book = db.execute_query("SELECT * FROM import_books WHERE book_id=%s", (book_id,), fetch_one=True)
    if not book: return {"status": "error", "msg": "书本不存在"}

    file_path = book['file_path']
    emit(f"📖 读取文件: {file_path}")

    parser = WordParser()
    try:
        segments = parser.parse_docx(file_path)
    except Exception as e:
        return {"status": "error", "msg": f"解析失败: {e}"}

    if not segments:
        return {"status": "error", "msg": "文档内容为空"}

    emit(f"✅ 解析完成，共 {len(segments)} 个段落。正在写入数据库...")

    try:
        conn = db.get_connection()
        with conn.cursor() as cursor:
            # 清理旧数据
            cursor.execute("DELETE FROM book_segments WHERE book_id=%s", (book_id,))
            cursor.execute("DELETE FROM knowledge_fragments WHERE book_id=%s", (book_id,))

            # 批量写入
            sql = "INSERT INTO book_segments (book_id, book_name, content, segment_order, is_processed) VALUES (%s, %s, %s, %s, 0)"
            params = [(book_id, book['book_name'], seg, i + 1) for i, seg in enumerate(segments)]
            cursor.executemany(sql, params)

            # 更新状态
            cursor.execute(
                "UPDATE import_books SET total_segments=%s, processed_segments=0, total_fragments=0, imported_fragments=0 WHERE book_id=%s",
                (len(segments), book_id))
            conn.commit()

        emit(f"🎉 切分入库成功！")
        return {"status": "success", "msg": f"切分完成，共 {len(segments)} 段"}
    except Exception as e:
        return {"status": "error", "msg": f"数据库错误: {e}"}