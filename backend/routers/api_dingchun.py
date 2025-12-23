import queue
import threading
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# === 路径修复 ===
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# === 业务模块导入 ===
from backend.dingchun.dingchun import dingchun
from backend.dingchun.call_other_ai import other_ai
from backend.tools.global_context import log_queue_ctx

router = APIRouter()

# 配置
DINGCHUN_MODE = "LOCAL"


class ToolInvokeRequest(BaseModel):
    question_id: int
    ai_type: str


# ==================== B. AI 工具接口 ====================
@router.post("/api/tool/review")
def trigger_review(req: ToolInvokeRequest):
    q_id = req.question_id

    # 1. 定春 (流式)
    if req.ai_type == "dingchun":
        q = queue.Queue()

        def event_stream():
            def run_task():
                token = log_queue_ctx.set(q)
                try:
                    result = dingchun.review_and_save(q_id, model_type=DINGCHUN_MODE)
                    q.put(f"DATA: {json.dumps(result, ensure_ascii=False)}")
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

    # 2. 其他 AI (非流式)
    try:
        if req.ai_type == "qwen":
            return other_ai.review_by_qwen(q_id)
        elif req.ai_type == "kimi":
            return other_ai.review_by_kimi(q_id)
        elif req.ai_type == "doubao":
            return other_ai.review_by_doubao(q_id)
        else:
            return {"status": "error", "msg": f"未知的 AI 类型: {req.ai_type}"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}