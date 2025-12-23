import queue
import threading
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any

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

# === 模型定义 ===
class BookTaskRequest(BaseModel):
    book_id: int

class BookSaveRequest(BaseModel):
    book_id: Optional[int] = None
    book_name: str
    file_path: str
    target_collection: str
    batch_size: int = 15

# ==================== 核心接口 ====================

# 1. 获取书本列表 (统一使用这个接口)
@router.post("/api/import/book/list")
def api_import_book_list():
    """
    获取所有书本列表 (无分页，简单粗暴，兼容性强)
    """
    try:
        # 【修正】补充 file_path, target_collection, imported_fragments, total_fragments, batch_size 等字段
        sql = """
            SELECT 
                book_id, book_name, file_path, target_collection, 
                batch_size, status,
                total_segments, processed_segments, 
                total_fragments, imported_fragments
            FROM import_books 
            ORDER BY book_id DESC
        """
        res = db.execute_query(sql)
        return {"status": "success", "data": res}
    except Exception as e:
        print(f"❌ 查询书本失败: {e}")
        return {"status": "error", "data": [], "msg": str(e)}

# 2. 保存书本
@router.post("/api/import/book/save")
def api_import_book_save(req: BookSaveRequest):
    try:
        if req.book_id:
            sql = "UPDATE import_books SET book_name=%s, file_path=%s, target_collection=%s, batch_size=%s WHERE book_id=%s"
            db.execute_update(sql, (req.book_name, req.file_path, req.target_collection, req.batch_size, req.book_id))
            return {"status": "success", "msg": "更新成功"}
        else:
            sql = "INSERT INTO import_books (book_name, file_path, target_collection, batch_size, status) VALUES (%s, %s, %s, %s, 'ready')"
            db.execute_update(sql, (req.book_name, req.file_path, req.target_collection, req.batch_size))
            return {"status": "success", "msg": "创建成功"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}

# 3. 删除书本
@router.post("/api/import/book/delete")
def api_import_book_delete(req: BookTaskRequest):
    try:
        db.execute_update("DELETE FROM import_books WHERE book_id=%s", (req.book_id,))
        return {"status": "success", "msg": "删除成功"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}

# 4. 执行任务流 (切分、处理、入库)
@router.post("/api/import/task/run")
def api_run_import_task(req: BookTaskRequest, step: str):
    q = queue.Queue()
    def event_stream():
        def run_task():
            token = log_queue_ctx.set(q)
            try:
                if step == 'split': execute_split_task(req.book_id)
                elif step == 'process': execute_process_task(req.book_id)
                elif step == 'embed': execute_embed_task(req.book_id)
                q.put(f"DATA: {json.dumps({'status': 'success'}, ensure_ascii=False)}")
            except Exception as e:
                q.put(f"DATA: {json.dumps({'status': 'error', 'msg': str(e)}, ensure_ascii=False)}")
            finally:
                q.put("[DONE]")
                try: log_queue_ctx.reset(token)
                except: pass
        t = threading.Thread(target=run_task)
        t.start()
        while True:
            msg = q.get()
            if msg == "[DONE]": break
            yield msg + "\n"
    return StreamingResponse(event_stream(), media_type="text/plain")