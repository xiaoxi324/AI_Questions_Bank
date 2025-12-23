import os
import sys
import uuid
from typing import List, Optional
from pydantic import BaseModel

# 路径修复
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from backend.tools.tools_sql_connect import db
from backend.tools.tools_call_ai import call_ai_emb
from config import config


# ================= 请求模型 (已适配 L1-L8) =================
class AuditQueryRequest(BaseModel):
    book_id: int
    current_range_index: int = 0


class AuditSearchRequest(BaseModel):
    book_id: int
    keyword: str


class BatchImportRequest(BaseModel):
    fragment_ids: List[int]


class FragmentSaveRequest(BaseModel):
    fragment_id: Optional[int] = None
    book_id: int
    book_name: str
    # 替换旧字段为 L1-L8
    L1: str = ""
    L2: str = ""
    L3: str = ""
    L4: str = ""
    L5: str = ""
    L6: str = ""
    L7: str = ""
    L8: str = ""
    combo_title: str = ""  # 组合标题
    content: str
    source_segment_range: str


# ================= 核心逻辑 =================

def get_book_ranges(book_id: int):
    """
    获取这本书所有的分段范围
    """
    sql = """
    SELECT source_segment_range 
    FROM knowledge_fragments 
    WHERE book_id = %s 
    GROUP BY source_segment_range 
    ORDER BY MIN(fragment_id) ASC
    """
    try:
        res = db.execute_query(sql, (book_id,))
        ranges = [r['source_segment_range'] for r in res if r.get('source_segment_range')]
        return ranges
    except Exception as e:
        print(f"❌ 获取范围失败: {e}")
        return []


def get_fragments_by_range(book_id: int, range_str: str):
    """获取指定范围内的所有片段"""
    sql = "SELECT * FROM knowledge_fragments WHERE book_id = %s AND source_segment_range = %s ORDER BY fragment_id ASC"
    return db.execute_query(sql, (book_id, range_str))


def search_fragments_in_book(book_id: int, keyword: str):
    """
    搜索片段 (适配 L1-L8 搜索)
    """
    if keyword.isdigit():
        sql = "SELECT * FROM knowledge_fragments WHERE book_id = %s AND fragment_id = %s"
        return db.execute_query(sql, (book_id, keyword))
    else:
        # 修改：搜索 content 和 combo_title
        sql = """
        SELECT * FROM knowledge_fragments 
        WHERE book_id = %s AND (content LIKE %s OR combo_title LIKE %s)
        LIMIT 50
        """
        pattern = f"%{keyword}%"
        return db.execute_query(sql, (book_id, pattern, pattern))


# ==========================================
# 👇 核心入库函数 (已适配 L1-L8) 👇
# ==========================================
def execute_batch_embed(fragment_ids: List[int]):
    """
    一键批量入库 (支持 Upsert 更新)
    """
    import chromadb

    if not fragment_ids: return {"status": "error", "msg": "未选择片段"}

    # 1. 查出片段
    format_strings = ','.join(['%s'] * len(fragment_ids))
    sql = f"SELECT * FROM knowledge_fragments WHERE fragment_id IN ({format_strings})"
    fragments = db.execute_query(sql, tuple(fragment_ids))

    if not fragments: return {"status": "error", "msg": "数据查询失败"}

    # 2. 获取集合名
    book_id = fragments[0]['book_id']
    book_info = db.execute_query("SELECT target_collection FROM import_books WHERE book_id=%s", (book_id,),
                                 fetch_one=True)
    col_name = book_info['target_collection'] if book_info else "Pharmacopoeia_Official"

    # 3. 连接 Chroma (确保路径正确)
    DB_PATH = getattr(config, "VECTOR_DB_PATH_MEDIC", "G:/KnowledgeBase/vectorizer_medic")

    try:
        client = chromadb.PersistentClient(path=DB_PATH)
        collection = client.get_or_create_collection(name=col_name)

        ids = []
        docs = []
        metadatas = []

        for frag in fragments:
            # 构造向量文本：标题 + 内容
            combo_title = frag.get('combo_title', '').strip()

            # 兜底：如果没有组合标题，尝试从 L 层级拼凑
            if not combo_title:
                parts = []
                for i in range(1, 9):
                    val = frag.get(f'L{i}')
                    if val: parts.append(val)
                combo_title = parts[-1] if parts else "无标题"

            vector_text = f"{combo_title}：\n{frag['content']}"

            # 构造完整路径 (L1 / L2 / ...)
            path_parts = []
            l_levels = {}  # 用于存入 metadata 的 L1-L8
            for i in range(1, 9):
                key = f"L{i}"
                val = frag.get(key, "")
                l_levels[key] = val  # 即使为空也存入，保持结构统一
                if val:
                    path_parts.append(val)

            full_path = " / ".join(path_parts)

            # 使用固定 UUID (基于 fragment_id)，确保多次入库是更新而不是重复
            stable_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"fragment_{frag['fragment_id']}"))

            ids.append(stable_uuid)
            docs.append(vector_text)

            # 构造符合新标准的元数据
            meta = {
                "来源文件": frag.get('book_name', ''),
                "组合标题": combo_title,
                "完整路径": full_path,
                "片段内容": frag['content'],
                "字数": len(frag['content']),
                "db_fragment_id": frag['fragment_id'],
                **l_levels  # 解包 L1-L8
            }
            metadatas.append(meta)

        # 4. 向量化
        embeddings = call_ai_emb(docs, dimensions=4096)
        if not embeddings: return {"status": "error", "msg": "向量化失败"}

        # 5. 写入 (使用 upsert)
        collection.upsert(ids=ids, documents=docs, embeddings=embeddings, metadatas=metadatas)

        # 6. 更新状态
        db.execute_update(f"UPDATE knowledge_fragments SET is_embedded=1 WHERE fragment_id IN ({format_strings})",
                          tuple(fragment_ids))

        # 7. 更新书本统计
        db.execute_update("""
            UPDATE import_books SET 
            imported_fragments = (SELECT COUNT(*) FROM knowledge_fragments WHERE book_id=%s AND is_embedded=1),
            total_fragments = (SELECT COUNT(*) FROM knowledge_fragments WHERE book_id=%s)
            WHERE book_id=%s
        """, (book_id, book_id, book_id))

        return {"status": "success", "msg": f"成功入库 {len(docs)} 条"}

    except Exception as e:
        return {"status": "error", "msg": str(e)}