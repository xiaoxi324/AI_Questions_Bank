from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

# 导入核心逻辑
from backend.dingchun import batch_review

router = APIRouter()


# --- 请求模型 ---
class StartBatchRequest(BaseModel):
    start_id: int
    end_id: int
    ai_list: List[str]


class StopBatchRequest(BaseModel):
    confirm: bool


# --- 接口 ---

@router.post("/api/batch/start")
def api_start_batch(req: StartBatchRequest):
    """
    开始新任务：
    1. 前端传 1-100 和 ["dingchun", "qwen"]
    2. 后端直接根据 question_review_details 算出哪些是 DONE，哪些是 WAIT
    3. 启动线程处理 WAIT
    """
    if req.start_id > req.end_id:
        return {"status": "error", "msg": "起始题号错误"}
    if not req.ai_list:
        return {"status": "error", "msg": "请选择AI"}

    return batch_review.start_new_batch(req.start_id, req.end_id, req.ai_list)


@router.post("/api/batch/stop")
def api_stop_batch(req: StopBatchRequest):
    return batch_review.stop_batch()


@router.get("/api/batch/progress")
def api_get_progress(page: int = 1, page_size: int = 20):
    """
    轮询接口。
    前端JS每秒调一次，直接用返回的 rows 渲染表格，用 stats 渲染顶部统计。
    """
    return batch_review.get_current_progress(page, page_size)