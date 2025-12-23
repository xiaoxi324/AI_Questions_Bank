from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional

# === 路径修复 ===
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# === 业务模块导入 ===
from backend.tools.tools_sql_connect import db
from backend.tools.tools_structure import add_question_to_db
from backend.knowledge.knowledge_audit import (
    get_book_ranges,
    get_fragments_by_range,
    execute_batch_embed,
    AuditQueryRequest,
    BatchImportRequest
    # FragmentSaveRequest 在下面重新定义了，这里可以去掉或保留，下面会覆盖
)

router = APIRouter()


# 1. 【核心修复】重新定义保存请求模型，匹配前端发送的字段
class FragmentSaveRequest(BaseModel):
    fragment_id: Optional[int] = None
    book_id: int
    book_name: Optional[str] = ""
    source_segment_range: Optional[str] = ""
    content: str
    # 必须加上 L1-L8 和 combo_title，否则报 422
    L1: Optional[str] = ""
    L2: Optional[str] = ""
    L3: Optional[str] = ""
    L4: Optional[str] = ""
    L5: Optional[str] = ""
    L6: Optional[str] = ""
    L7: Optional[str] = ""
    L8: Optional[str] = ""
    combo_title: Optional[str] = ""


# === 请求模型 ===
class DataManageRequest(BaseModel):
    action: str
    payload: Dict[str, Any]


class ListQueryRequest(BaseModel):
    page: int = 1
    page_size: int = 50
    search_text: Optional[str] = None


class HistoryQueryRequest(BaseModel):
    question_id: int


class BookTaskRequest(BaseModel):
    book_id: int


class BatchStatusRequest(BaseModel):
    start_id: int
    end_id: int


# ==================== A. 题库数据接口 ====================

@router.post("/api/data/question/manage")
def manage_questions(req: DataManageRequest):
    try:
        if req.action == "add":
            raw_text = req.payload.get("raw_text")
            source = req.payload.get("source", "智能审题")
            if not raw_text: return {"status": "error", "msg": "内容不能为空"}
            return add_question_to_db(raw_text, source)

        elif req.action == "delete":
            q_id = req.payload.get("id")
            if not q_id: return {"status": "error", "msg": "ID不能为空"}
            sql = "DELETE FROM pharmacist_questions WHERE question_id = %s"
            res = db.execute_update(sql, (q_id,))
            return {"status": "success", "msg": "删除成功"} if res else {"status": "error", "msg": "删除失败"}

        elif req.action == "update":
            data = req.payload
            q_id = data.get("question_id")
            if not q_id: return {"status": "error", "msg": "ID为空"}

            # ✅ [修复] 动态构建 SQL，支持所有 12 个选项 (A-L)
            sql = """
            UPDATE pharmacist_questions SET 
                stem=%s, 
                option_a=%s, option_b=%s, option_c=%s, option_d=%s, option_e=%s, 
                option_f=%s, option_g=%s, option_h=%s, option_i=%s, option_j=%s, option_k=%s, option_l=%s,
                answer=%s, analysis=%s 
            WHERE question_id=%s
            """

            params = (
                data.get("stem"),
                data.get("option_a"), data.get("option_b"), data.get("option_c"), data.get("option_d"),
                data.get("option_e"),
                data.get("option_f"), data.get("option_g"), data.get("option_h"), data.get("option_i"),
                data.get("option_j"), data.get("option_k"), data.get("option_l"),
                data.get("answer"), data.get("analysis"),
                q_id
            )

            db.execute_update(sql, params)
            return {"status": "success", "msg": "更新成功"}
        else:
            return {"status": "error", "msg": f"未知操作: {req.action}"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


@router.post("/api/data/question/list")
def list_questions(req: ListQueryRequest):
    offset = (req.page - 1) * req.page_size
    where_clause = "1=1"
    params = []
    if req.search_text:
        keyword = f"%{req.search_text}%"
        if req.search_text.isdigit():
            where_clause += " AND (question_id = %s OR stem LIKE %s)"
            params.extend([req.search_text, keyword])
        else:
            where_clause += " AND stem LIKE %s"
            params.append(keyword)

    sql = f"""
    SELECT q.*,
        (SELECT review_result FROM question_review_details WHERE question_id = q.question_id AND ai_name LIKE '定春%%' ORDER BY review_time DESC LIMIT 1) as status_dingchun,
        (SELECT review_result FROM question_review_details WHERE question_id = q.question_id AND ai_name LIKE 'Qwen%%' ORDER BY review_time DESC LIMIT 1) as status_qwen,
        (SELECT review_result FROM question_review_details WHERE question_id = q.question_id AND ai_name LIKE 'Kimi%%' ORDER BY review_time DESC LIMIT 1) as status_kimi,
        (SELECT review_result FROM question_review_details WHERE question_id = q.question_id AND ai_name LIKE 'Doubao%%' ORDER BY review_time DESC LIMIT 1) as status_doubao
    FROM pharmacist_questions q
    WHERE {where_clause}
    ORDER BY q.question_id DESC LIMIT %s OFFSET %s
    """
    rows = db.execute_query(sql, tuple(params + [req.page_size, offset]))

    count_sql = f"SELECT COUNT(*) as total FROM pharmacist_questions WHERE {where_clause}"
    total_res = db.execute_query(count_sql, tuple(params), fetch_one=True)
    total = total_res['total'] if total_res else 0

    for row in rows:
        # ✅ [修复] 扩展到 12 个选项 (a - l) 用于前端列表预览
        options_str = []
        full_options = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l']

        for char in full_options:
            val = row.get(f'option_{char}')
            if val: options_str.append(f"{char.upper()}.{val}")

        row['options_display'] = "  ".join(options_str)

        # ✅ [修复] 解决 AttributeError: 'str' object has no attribute 'strftime'
        # 兼容数据库返回 datetime 对象或 str 字符串的情况
        if row.get('create_time'):
            if hasattr(row['create_time'], 'strftime'):
                row['create_time'] = row['create_time'].strftime("%Y-%m-%d %H:%M")
            else:
                # 如果是字符串，截取前16位 (yyyy-mm-dd HH:MM)
                row['create_time'] = str(row['create_time'])[:16]

        for key in ['status_dingchun', 'status_qwen', 'status_kimi', 'status_doubao']:
            if not row.get(key): row[key] = '未执行'

    return {"status": "success", "data": rows, "total": total, "page": req.page}


@router.post("/api/data/review/history")
def get_review_history(req: HistoryQueryRequest):
    def get_all_by_ai(pattern):
        sql = "SELECT review_id, review_result, review_content, rag_index, review_time FROM question_review_details WHERE question_id = %s AND ai_name LIKE %s ORDER BY review_time DESC"
        return db.execute_query(sql, (req.question_id, pattern))

    try:
        data_map = {
            "dingchun": get_all_by_ai('定春%'),
            "qwen": get_all_by_ai('Qwen%'),
            "kimi": get_all_by_ai('Kimi%'),
            "doubao": get_all_by_ai('Doubao%')
        }
        for key, val in data_map.items():
            for record in val:
                # 这里也加上类型检查比较稳妥，不过通常 history 接口不容易挂
                if record.get('review_time'):
                    if hasattr(record['review_time'], 'strftime'):
                        record['review_time'] = record['review_time'].strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        record['review_time'] = str(record['review_time'])[:19]

        return {"status": "success", "data": data_map}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


# === 新增：批量状态查询接口 (用于前端批量审题页面) ===
@router.post("/api/data/batch/status")
def api_batch_status(req: BatchStatusRequest):
    sql = """
    SELECT q.question_id, left(q.stem, 20) as stem_preview,
        (SELECT review_result FROM question_review_details WHERE question_id = q.question_id AND ai_name LIKE '定春%%' ORDER BY review_time DESC LIMIT 1) as status_dingchun,
        (SELECT review_result FROM question_review_details WHERE question_id = q.question_id AND ai_name LIKE 'Qwen%%' ORDER BY review_time DESC LIMIT 1) as status_qwen,
        (SELECT review_result FROM question_review_details WHERE question_id = q.question_id AND ai_name LIKE 'Kimi%%' ORDER BY review_time DESC LIMIT 1) as status_kimi,
        (SELECT review_result FROM question_review_details WHERE question_id = q.question_id AND ai_name LIKE 'Doubao%%' ORDER BY review_time DESC LIMIT 1) as status_doubao
    FROM pharmacist_questions q
    WHERE q.question_id BETWEEN %s AND %s
    ORDER BY q.question_id ASC
    """
    data = db.execute_query(sql, (req.start_id, req.end_id))
    return {"status": "success", "data": data}


# ==================== F. 知识审核接口 (归类为SQL操作) ====================

@router.post("/api/audit/ranges")
def api_audit_ranges(req: BookTaskRequest):
    ranges = get_book_ranges(req.book_id)
    return {"status": "success", "data": ranges}


@router.post("/api/audit/list")
def api_audit_list(req: AuditQueryRequest):
    ranges = get_book_ranges(req.book_id)
    if not ranges:
        return {"status": "success", "data": [], "total_batches": 0, "current_range": ""}
    idx = req.current_range_index
    if idx >= len(ranges): idx = len(ranges) - 1
    if idx < 0: idx = 0
    current_range = ranges[idx]
    data = get_fragments_by_range(req.book_id, current_range)
    return {
        "status": "success",
        "data": data,
        "total_batches": len(ranges),
        "current_batch_idx": idx,
        "current_range": current_range
    }


@router.post("/api/audit/embed_batch")
def api_audit_embed(req: BatchImportRequest):
    return execute_batch_embed(req.fragment_ids)


@router.post("/api/audit/save_fragment")
def api_audit_save_fragment(req: FragmentSaveRequest):
    try:
        if req.fragment_id:
            # === 更新逻辑 ===
            sql = """
            UPDATE knowledge_fragments 
            SET L1=%s, L2=%s, L3=%s, L4=%s, L5=%s, L6=%s, L7=%s, L8=%s, 
                combo_title=%s, content=%s, source_segment_range=%s
            WHERE fragment_id=%s
            """
            params = (
                req.L1, req.L2, req.L3, req.L4, req.L5, req.L6, req.L7, req.L8,
                req.combo_title, req.content, req.source_segment_range,
                req.fragment_id
            )
            db.execute_update(sql, params)
        else:
            # === 新增逻辑 ===
            sql = """
            INSERT INTO knowledge_fragments 
            (book_id, book_name, source_segment_range, content, is_embedded,
             L1, L2, L3, L4, L5, L6, L7, L8, combo_title)
            VALUES (%s, %s, %s, %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                req.book_id, req.book_name, req.source_segment_range, req.content,
                req.L1, req.L2, req.L3, req.L4, req.L5, req.L6, req.L7, req.L8, req.combo_title
            )
            db.execute_update(sql, params)

        return {"status": "success", "msg": "保存成功"}
    except Exception as e:
        print(f"❌ 保存失败: {e}")
        return {"status": "error", "msg": str(e)}


@router.post("/api/audit/delete_fragment")
def api_audit_delete_fragment(req: Dict[str, int]):
    db.execute_update("DELETE FROM knowledge_fragments WHERE fragment_id=%s", (req['fragment_id'],))
    return {"status": "success"}