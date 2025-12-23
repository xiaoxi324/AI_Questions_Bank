from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, List
import json
import sys
import os

# === 路径修复 ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# === 业务模块导入 ===
# 1. 搜索工具 (Search Tool)
from backend.search.search_tool import (
    handle_tool_search,
    handle_tool_update,
    SearchToolRequest,
    KnowledgeUpdateRequest
)

# 2. [新增] 级标搜索工具 (Level Lookup)
from backend.search.level_lookup import (
    execute_level_lookup,
    LevelLookupRequest
)

# 3. 知识库管理 (Knowledge Tool)
from backend.knowledge.knowledge_tool import (
    list_collections,
    get_metadata_values,
    query_documents,
    save_document,
    delete_document,
    get_database_overview,
    QueryRequest as KBQueryRequest,
    DocumentRequest as KBDocumentRequest,
    DeleteRequest as KBDeleteRequest
)

from backend.tools.tools_sql_connect import db

router = APIRouter()

# ==================== C. 搜索工具接口 ====================

@router.post("/api/tool/search")
def search_knowledge_base(req: SearchToolRequest):
    """
    通用搜索接口 (全库模糊检索 + 语义检索)
    """
    return handle_tool_search(req)

@router.post("/api/tool/update_rag")
def update_knowledge_base_item(req: KnowledgeUpdateRequest):
    """
    搜索结果反馈更新接口
    """
    return handle_tool_update(req)

@router.post("/api/tool/level_lookup")
def level_lookup_search(req: LevelLookupRequest):
    """
    [新增] 级标定向检索接口
    先通过 title_filter 过滤范围，再通过 search_content 进行语义比对
    """
    return execute_level_lookup(req)

# ==================== D. 知识库管理接口 ====================

@router.get("/api/knowledge/collections")
def api_list_collections():
    """获取简单的集合名称列表 (旧接口保留)"""
    return {"status": "success", "data": list_collections()}

@router.get("/api/knowledge/overview")
def api_get_db_overview():
    """
    [新增] 获取详细概览：包含集合、数据总量、来源文件及各文件条目数
    用于 Config 页面展示
    """
    return get_database_overview()

@router.get("/api/knowledge/meta_keys")
def api_get_meta_keys(collection: str = "Pharmacopoeia"):
    return {"status": "success", "data": get_metadata_values(collection)}

@router.post("/api/knowledge/query")
def api_query_docs(req: KBQueryRequest):
    return query_documents(req)

@router.post("/api/knowledge/save")
def api_save_doc(req: KBDocumentRequest):
    return save_document(req)

@router.post("/api/knowledge/delete")
def api_delete_doc(req: KBDeleteRequest):
    return delete_document(req)


# ==================== E. 系统配置接口 ====================

@router.get("/api/config/get")
def get_system_config(key: str):
    """
    从数据库读取配置
    """
    sql = "SELECT config_value FROM system_config WHERE config_key = %s"
    res = db.execute_query(sql, (key,), fetch_one=True)

    if res and res['config_value']:
        try:
            # 尝试解析 JSON (例如列表 ["a", "b"])
            return {"status": "success", "data": json.loads(res['config_value'])}
        except:
            # 如果不是 JSON，直接返回字符串
            return {"status": "success", "data": res['config_value']}

    # 如果没找到配置，返回 null
    return {"status": "success", "data": None}


# 定义配置保存请求体
class ConfigRequest(BaseModel):
    config_key: str
    value: Any

@router.post("/api/config/save")
def save_system_config(req: ConfigRequest):
    """
    保存配置到数据库 (前端复选框保存用)
    """
    # 将值转换为 JSON 字符串存储
    val_str = json.dumps(req.value, ensure_ascii=False)

    sql = """
    INSERT INTO system_config (config_key, config_value) 
    VALUES (%s, %s) 
    ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)
    """
    try:
        db.execute_update(sql, (req.config_key, val_str))
        return {"status": "success", "msg": "配置已保存"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}