import os
import json
import re
from docx import Document
from docx.document import Document as _Document
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph


# ================== 配置 ==================
class Config:
    # 输入文件夹：存放 docx 的目录
    INPUT_DIR = r"G:\KnowledgeBase\整理好的原始文件"

    # 输出文件夹：存放 json 的目录
    OUTPUT_DIR = r"G:\KnowledgeBase\分词后数据"


config = Config()


# ================== 核心工具函数 ==================

def iter_block_items(parent):
    """
    生成器：按文档顺序遍历 docx 中的所有内容（包括段落和表格）。
    """
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


def table_to_markdown(table) -> str:
    """
    将 docx 表格对象转换为 Markdown 字符串
    """
    if not table.rows:
        return ""

    rows_content = []
    for row in table.rows:
        row_cells = []
        for cell in row.cells:
            # 清洗单元格内的换行符
            cell_text = cell.text.strip().replace('\n', '<br>')
            row_cells.append(cell_text)
        rows_content.append(row_cells)

    if not rows_content:
        return ""

    lines = []
    # 1. 表头
    headers = rows_content[0]
    lines.append("| " + " | ".join(headers) + " |")
    # 2. 分隔线
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    # 3. 数据行
    if len(rows_content) > 1:
        for row in rows_content[1:]:
            while len(row) < len(headers):
                row.append("")
            row = row[:len(headers)]
            lines.append("| " + " | ".join(row) + " |")

    return "\n" + "\n".join(lines) + "\n"


def clean_text(text):
    """简单的文本清洗"""
    if not text:
        return ""
    return text.strip()


# ================== 处理逻辑 ==================

def process_annotated_docx(docx_path):
    """处理标注好的文档，剔除标题本身，保留表格"""
    try:
        doc = Document(docx_path)
    except Exception as e:
        print(f"❌ 读取文件失败: {docx_path}, 错误: {e}")
        return []

    file_name = os.path.basename(docx_path)
    fragments = []

    # 定义最大层级
    MAX_LEVEL = 8

    # 初始化上下文
    current_context = {
        "来源文件": file_name,
        "完整路径": "",
        "组合标题": ""
    }
    for i in range(1, MAX_LEVEL + 1):
        current_context[f"L{i}"] = ""

    current_content = []

    def get_context_title():
        """生成通用组合标题 (向上找2层)"""
        deepest_level = 0
        for i in range(MAX_LEVEL, 0, -1):
            if current_context[f"L{i}"]:
                deepest_level = i
                break
        if deepest_level == 0:
            return ""
        start_level = max(1, deepest_level - 2)
        title_parts = []
        for i in range(start_level, deepest_level + 1):
            val = current_context[f"L{i}"]
            if val:
                title_parts.append(val)
        return " - ".join(title_parts)

    def save_fragment():
        """保存当前片段"""
        if current_content:
            content_text = "\n".join([txt for txt in current_content if txt.strip()])

            if content_text:
                fragment = current_context.copy()
                fragment["片段内容"] = content_text
                fragment["字数"] = len(content_text)

                # A. 构建完整路径
                path_items = []
                for i in range(1, MAX_LEVEL + 1):
                    val = fragment[f"L{i}"]
                    if val:
                        path_items.append(val)
                full_path_str = "/".join(path_items)
                fragment["完整路径"] = full_path_str

                # B. 组合标题
                fragment["组合标题"] = get_context_title()

                # C. 向量文本 (核心修改：完整路径 + 纯净内容)
                # 这样检索时包含标题语义，但展示时没有标题干扰
                fragment["向量文本"] = f"{full_path_str}：\n{content_text}"

                fragments.append(fragment)

            current_content.clear()

    print(f"🚀 正在切分: {file_name} ...")

    for block in iter_block_items(doc):

        # --- 情况1: 遇到段落 ---
        if isinstance(block, Paragraph):
            text = clean_text(block.text)
            if not text:
                continue

            style = block.style.name
            is_heading = False
            level = 0

            # 判断标题层级
            match = re.match(r'^(Heading|标题)\s*([1-8])$', style, re.IGNORECASE)
            if match:
                level = int(match.group(2))
                is_heading = True
            else:
                try:
                    if 0 <= block.paragraph_format.outline_level <= 7:
                        level = block.paragraph_format.outline_level + 1
                        is_heading = True
                except:
                    pass

            if is_heading:
                # 1. 遇到新标题，先把【上一段】的内容存盘
                save_fragment()

                # 2. 【核心修改】不要把标题本身加入 current_content
                # current_content.append(text)  <-- 这一行删掉了

                # 3. 更新上下文层级 (标题只存在于 Metadata 和 路径中)
                if 1 <= level <= MAX_LEVEL:
                    current_context[f"L{level}"] = text
                    # 清空子层级
                    for d in range(level + 1, MAX_LEVEL + 1):
                        current_context[f"L{d}"] = ""
            else:
                # 普通段落才加入内容
                current_content.append(text)

        # --- 情况2: 遇到表格 ---
        elif isinstance(block, Table):
            print(f"   Detected Table ({len(block.rows)} rows)")
            table_md = table_to_markdown(block)
            if table_md:
                current_content.append(table_md)

    # 循环结束后保存最后一段
    save_fragment()
    return fragments


def batch_process_annotated_docs():
    """批量处理指定目录下的所有 docx"""
    input_dir = config.INPUT_DIR
    output_dir = config.OUTPUT_DIR

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    if not os.path.exists(input_dir):
        print(f"❌ 输入目录不存在: {input_dir}")
        return

    docx_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.docx') and not f.startswith('~$')]

    if not docx_files:
        print("⚠️ 目录下没有找到 .docx 文件")
        return

    print(f"📂 发现 {len(docx_files)} 个文档，准备处理...")

    for doc_file in docx_files:
        full_input_path = os.path.join(input_dir, doc_file)

        data = process_annotated_docx(full_input_path)

        if data:
            json_name = os.path.splitext(doc_file)[0] + ".json"
            out_path = os.path.join(output_dir, json_name)

            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"✅ 保存成功 ({len(data)} 片段): {json_name}")
        else:
            print(f"⚠️ 跳过空文件或解析失败: {doc_file}")


if __name__ == "__main__":
    batch_process_annotated_docs()