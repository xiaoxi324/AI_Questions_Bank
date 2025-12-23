import sys
import os
import json
import queue
from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Generator, Literal

# === 路径修复 ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入 QuestionPipeline 和 工具
try:
    from backend.question_agent.z_common import QuestionPipeline
    from backend.tools.tools_sql_connect import db
    from backend.tools.global_context import log_queue_ctx
except ImportError as e:
    print(f"FATAL: Agent core or DB tools not found: {e}")
    sys.exit(1)

router = APIRouter()
pipeline = QuestionPipeline()


# === 1. 请求模型定义 ===
class QuestionParams(BaseModel):
    topic: str = Field(..., description="考点/知识点")
    has_case: bool = Field(..., description="是否生成案例 (True=生成, False=无案例)")
    correct_count: int = Field(..., description="正确选项数")
    total_count: int = Field(..., description="总选项数")
    question_count: int = Field(default=1, description="生成的题目数量")


def derive_question_type(has_case: bool, correct_count: int) -> str:
    if has_case:
        return "案例分析题"
    if correct_count > 1:
        return "多选题"
    return "A型题"


def mixed_stream_generator(pipeline_generator: Generator[Dict, None, None], log_queue: queue.Queue) -> Generator[
    str, None, None]:
    """
    混合流生成器：负责格式标准化
    """

    def yield_queue_logs():
        """优先推送工具产生的片段"""
        while not log_queue.empty():
            try:
                log = log_queue.get_nowait()
                # 工具层已经封装好了 {"type": "snippet", "content": ...}
                yield f"data: {json.dumps(log, ensure_ascii=False)}\n\n"
            except queue.Empty:
                break

    for item in pipeline_generator:
        # 1. 先把积压的工具日志吐出来
        yield from yield_queue_logs()

        # 2. 格式化 Agent 主流程数据 (关键修复)
        # z_common 返回的可能是 {"stage": "...", "stream": "..."}
        # 前端 JS 需要 {"type": "process", "content": "..."}

        payload = {}

        # 复制原始字段
        for k, v in item.items():
            payload[k] = v

        # [核心修复逻辑] 字段映射
        if "type" not in payload:
            # 如果没有 type，默认为 process (日志)
            if "stream" in payload or "stage" in payload:
                payload["type"] = "process"

        # 将 stream 映射为 content (前端只读 content)
        if "content" not in payload and "stream" in payload:
            payload["content"] = payload["stream"]

        # 过滤掉不需要发给前端的 type (防止重复)
        if payload.get("type") == "snippet":
            continue

        try:
            # 序列化时处理无法 JSON 化的对象
            safe_payload = {
                k: str(v) if not isinstance(v, (str, int, float, bool, dict, list, type(None))) else v
                for k, v in payload.items()
            }
            json_data = json.dumps(safe_payload, ensure_ascii=False)
            yield f"data: {json_data}\n\n"
        except Exception as e:
            err = {"type": "error", "content": f"JSON序列化失败: {str(e)}"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

        # 结束标志
        if item.get("completion"):
            yield from yield_queue_logs()  # 再次检查遗漏日志
            # 注意：不立即 break，允许 z_common 继续 yield 下一道题的 completion
            # 只有当 z_common 明确 yield {"stage": "Done"} 时才算真正结束
            pass

    # 循环彻底结束
    yield from yield_queue_logs()
    yield "data: [DONE]\n\n"


@router.post("/api/generate/question")
async def generate_exam_question(params: QuestionParams):
    try:
        q_type = derive_question_type(params.has_case, params.correct_count)

        pipeline_params = {
            "topic": params.topic,
            "type": q_type,
            "correct_count": params.correct_count,
            "total_count": params.total_count,
            "has_case": params.has_case,
            "question_count": params.question_count
        }

        q = queue.Queue()
        token = log_queue_ctx.set(q)

        generator = pipeline.generate_full_question(pipeline_params)

        return StreamingResponse(
            mixed_stream_generator(generator, q),
            media_type="text/event-stream"
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"服务启动失败: {str(e)}"}
        )


# ... (save_final_question 保持不变) ...
@router.post("/api/question/save_to_db")
def save_final_question(db_record: Dict[str, Any]):
    sql = """
    INSERT INTO pharmacist_questions (
        question_type, case_content, stem, 
        option_a, option_b, option_c, option_d, option_e, option_f, 
        option_g, option_h, option_i, option_j, option_k, option_l,
        answer, analysis, source, create_time
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    """
    try:
        params = (
            db_record.get('question_type', 'A型题'),
            db_record.get('case_content', ''),
            db_record.get('stem', ''),
            db_record.get('option_a'), db_record.get('option_b'), db_record.get('option_c'),
            db_record.get('option_d'), db_record.get('option_e'), db_record.get('option_f'),
            db_record.get('option_g'), db_record.get('option_h'), db_record.get('option_i'),
            db_record.get('option_j'), db_record.get('option_k'), db_record.get('option_l'),
            db_record.get('answer', ''),
            db_record.get('analysis', ''),
            db_record.get('source', '智能编题')
        )
        db.execute_update(sql, params)
        return {"status": "success", "message": "入库成功"}
    except Exception as e:
        return {"status": "error", "message": f"数据库错误: {str(e)}"}