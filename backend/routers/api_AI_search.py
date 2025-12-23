from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from backend.tools.tools_sql_connect import db
from backend.search.AI_search import process_text_comparison
from fastapi.responses import StreamingResponse

router = APIRouter()


# === 请求模型 ===

class BookContentRequest(BaseModel):
    book_id: int
    start_row: int
    end_row: int


class TextComparisonRequest(BaseModel):
    text: str


# 新增：书本列表请求模型
class BookListRequest(BaseModel):
    page: int = 1
    page_size: int = 100


# === 接口定义 ===
# 2. 获取指定书本的指定行内容
@router.post("/api/smart_compare/get_book_content")
def get_book_content(req: BookContentRequest):
    """
    Get content from book_segments based on book_id and segment_order range.
    """
    try:
        # Assuming segment_order roughly maps to 'rows' or logical segments as per import logic
        sql = """
            SELECT content 
            FROM book_segments 
            WHERE book_id = %s AND segment_order BETWEEN %s AND %s 
            ORDER BY segment_order ASC
        """
        segments = db.execute_query(sql, (req.book_id, req.start_row, req.end_row))

        if not segments:
            return {"status": "success", "data": ""}

        # Join content with newlines
        full_text = "\n".join([seg['content'] for seg in segments if seg['content']])
        return {"status": "success", "data": full_text}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


# 3. 执行智能对比
@router.post("/api/smart_compare/process")
def smart_compare_process(req: TextComparisonRequest):
    """
    流式接口：即时返回每一条分析结果
    """
    if not req.text.strip():
        # 如果是流式响应，错误也得按流的方式或者直接抛异常，这里简单处理
        return {"status": "error", "msg": "输入内容不能为空"}

    # 调用生成器
    generator = process_text_comparison(req.text)

    # 返回流式响应，告诉浏览器这是 application/x-ndjson (换行分隔的JSON)
    return StreamingResponse(generator, media_type="application/x-ndjson")