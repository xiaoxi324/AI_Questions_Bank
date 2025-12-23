import queue
import threading
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

# === 路径修复 ===
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

from backend.tools.tools_sql_connect import db
from backend.tools.global_context import log_queue_ctx
from backend.books.tools_import_step1_split import execute_split_task
from backend.books.tools_import_step2_process import execute_process_task
from backend.books.tools_import_step3_embed import execute_embed_task

router = APIRouter()


# === 请求模型 ===
class BookTaskRequest(BaseModel):
    book_id: int


class BookSaveRequest(BaseModel):
    book_id: Optional[int] = None
    book_name: str
    file_path: str
    target_collection: str
    batch_size: int = 15


# 新增：用于标准列表查询
class BookListRequest(BaseModel):
    page: int = 1
    page_size: int = 100
    status: Optional[str] = None


# ==================== E. 智能录入接口 ====================

# 【旧接口】保留以兼容旧的“书本管理”页面
# 如果您的 import_books.js 还没有改为分页模式，请保留这个
@router.post("/api/import/book/list")
def api_import_book_list():
    sql = "SELECT * FROM import_books ORDER BY create_time DESC"
    res = db.execute_query(sql)
    return {"status": "success", "data": res}


# 【新标准接口】全系统通用（AI对比、知识审核、新版管理页都用这个）
# 从 api_AI_search.py 迁移至此
@router.post("/api/data/book/list")
def api_data_book_list(req: BookListRequest):
    """
    获取书本列表（支持分页和状态筛选）
    """
    try:
        offset = (req.page - 1) * req.page_size

        # 1. 查询数据
        sql = "SELECT book_id, book_name, status, total_segments, processed_segments, create_time FROM import_books"
        params = []

        if req.status:
            sql += " WHERE status = %s"
            params.append(req.status)

        sql += " ORDER BY book_id DESC LIMIT %s OFFSET %s"
        params.extend([req.page_size, offset])

        books = db.execute_query(sql, tuple(params))

        # 处理时间格式
        for b in books:
            if b.get('create_time'):
                b['create_time'] = b['create_time'].strftime("%Y-%m-%d %H:%M")

        # 2. 查询总数
        count_sql = "SELECT COUNT(*) as total FROM import_books"
        if req.status:
            count_sql += " WHERE status = %s"
            total_res = db.execute_query(count_sql, (req.status,), fetch_one=True)
        else:
            total_res = db.execute_query(count_sql, fetch_one=True)

        total = total_res['total'] if total_res else 0

        return {"status": "success", "data": books, "total": total}

    except Exception as e:
        print(f"❌ 获取书本列表失败: {e}")
        return {"status": "error", "msg": str(e)}


@router.post("/api/import/book/save")
def api_import_book_save(req: BookSaveRequest):
    if req.book_id:
        sql = "UPDATE import_books SET book_name=%s, file_path=%s, target_collection=%s, batch_size=%s WHERE book_id=%s"
        db.execute_update(sql, (req.book_name, req.file_path, req.target_collection, req.batch_size, req.book_id))
        return {"status": "success", "msg": "更新成功"}
    else:
        sql = "INSERT INTO import_books (book_name, file_path, target_collection, batch_size, status) VALUES (%s, %s, %s, %s, 'ready')"
        db.execute_update(sql, (req.book_name, req.file_path, req.target_collection, req.batch_size))
        return {"status": "success", "msg": "创建成功"}


@router.post("/api/import/book/delete")
def api_import_book_delete(req: BookTaskRequest):
    db.execute_update("DELETE FROM import_books WHERE book_id=%s", (req.book_id,))
    # 同时可以考虑删除相关的 segments 和 fragments，视需求而定
    return {"status": "success", "msg": "删除成功"}


@router.post("/api/import/task/run")
def api_run_import_task(req: BookTaskRequest, step: str):
    q = queue.Queue()

    def event_stream():
        def run_task():
            token = log_queue_ctx.set(q)
            try:
                if step == 'split':
                    execute_split_task(req.book_id)
                elif step == 'process':
                    execute_process_task(req.book_id)
                elif step == 'embed':
                    execute_embed_task(req.book_id)
                q.put(f"DATA: {json.dumps({'status': 'success'}, ensure_ascii=False)}")
            except Exception as e:
                q.put(f"DATA: {json.dumps({'status': 'error', 'msg': str(e)}, ensure_ascii=False)}")
            finally:
                q.put("[DONE]")
                try:
                    log_queue_ctx.reset(token)
                except:
                    pass

        t = threading.Thread(target=run_task)
        t.start()
        while True:
            msg = q.get()
            if msg == "[DONE]": break
            yield msg + "\n"

    return StreamingResponse(event_stream(), media_type="text/plain")