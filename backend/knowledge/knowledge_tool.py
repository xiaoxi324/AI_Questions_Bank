import os
import chromadb
import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel
from collections import Counter  # <--- [新增] 用于统计
from config import config
from backend.tools.tools_call_ai import call_ai_emb

# ==================== 基础配置 ====================
DB_PATH = getattr(config, "VECTOR_DB_PATH_MEDIC", "G:/KnowledgeBase/vectorizer_medic")
COLLECTION_NAME = "Pharmacopoeia_Official"
EMBEDDING_DIM = getattr(config, "EMBEDDING_DIM", 4096)


class ChromaAdmin:
    _client = None

    @classmethod
    def get_client(cls):
        if cls._client is None:
            if not os.path.exists(DB_PATH): return None
            try:
                cls._client = chromadb.PersistentClient(path=DB_PATH)
            except:
                return None
        return cls._client


# ==================== 请求模型 ====================
class CollectionRequest(BaseModel):
    collection_name: str


class QueryRequest(BaseModel):
    collection_name: str
    page: int = 1
    page_size: int = 20
    filters: Optional[Dict[str, Any]] = None


class DocumentRequest(BaseModel):
    collection_name: str
    doc_id: Optional[str] = None

    # 前端用户编辑的纯文本内容
    content: str

    # 前端传来的属性 (包括 L1-L8, 来源文件, 组合标题)
    metadata_raw: Dict[str, str]


class DeleteRequest(BaseModel):
    collection_name: str
    doc_id: str


# ==================== 核心功能 ====================

def list_collections():
    client = ChromaAdmin.get_client()
    if not client: return []
    return [c.name for c in client.list_collections()]


def get_metadata_values(collection_name: str):
    keys = ["来源文件", "组合标题"]
    keys.extend([f"L{i}" for i in range(1, 9)])
    return keys


def query_documents(req: QueryRequest):
    """
    分页查询 (逻辑不变)
    """
    client = ChromaAdmin.get_client()
    if not client: return {"status": "error", "msg": "DB未连接"}

    try:
        col = client.get_collection(req.collection_name)

        # 1. 获取所有 Metadata 用于过滤
        all_data = col.get(include=["metadatas"])
        all_ids = all_data['ids']
        all_metas = all_data['metadatas']

        matched_ids = []

        if req.filters:
            valid_filters = {k: v.strip() for k, v in req.filters.items() if v and v.strip()}
            if not valid_filters:
                matched_ids = all_ids
            else:
                for i, meta in enumerate(all_metas):
                    is_match = True
                    for k, v in valid_filters.items():
                        meta_val = str(meta.get(k, ""))
                        if v.lower() not in meta_val.lower():
                            is_match = False
                            break
                    if is_match:
                        matched_ids.append(all_ids[i])
        else:
            matched_ids = all_ids

        total_count = len(matched_ids)
        start = (req.page - 1) * req.page_size
        end = start + req.page_size
        page_ids = matched_ids[start:end]

        data = []
        if page_ids:
            details = col.get(ids=page_ids, include=["metadatas", "documents"])
            temp_dict = {}
            for i in range(len(details['ids'])):
                temp_dict[details['ids'][i]] = {
                    # documents 里存的是 "组合标题：\n内容"，取出来直接展示给前端没问题
                    # 或者前端只展示 metadata['片段内容'] 也可以
                    "content": details['documents'][i],
                    "metadata": details['metadatas'][i]
                }
            for pid in page_ids:
                if pid in temp_dict:
                    data.append({
                        "id": pid,
                        "content": temp_dict[pid]['content'],
                        "metadata": temp_dict[pid]['metadata']
                    })

        return {
            "status": "success",
            "data": data,
            "total": total_count,
            "page": req.page
        }

    except Exception as e:
        return {"status": "error", "msg": str(e)}


def save_document(req: DocumentRequest):
    """
    修改：确保将 (组合标题 + 内容) 存入 Vector Text
    """
    client = ChromaAdmin.get_client()
    if not client: return {"status": "error", "msg": "DB连接失败"}

    try:
        col = client.get_collection(req.collection_name)

        # 1. 获取基础数据
        m = req.metadata_raw
        source = m.get("来源文件", "").strip()

        # 用户编辑的纯内容
        raw_content = req.content.strip()

        # 2. 收集 L1-L8 并构建完整路径 (用于存 Metadata)
        l_levels = {}
        path_parts = []
        for i in range(1, 9):
            key = f"L{i}"
            val = m.get(key, "").strip()
            l_levels[key] = val
            if val:
                path_parts.append(val)

        full_path_str = " / ".join(path_parts)

        # 3. 获取或计算 "组合标题"
        # 优先用前端传来的，如果没有，后端计算 (倒序取最后3级)
        combo_title = m.get("组合标题", "").strip()
        if not combo_title and path_parts:
            # 取最后 3 个，倒序
            combo_title = " / ".join(path_parts[-3:][::-1])

        if not combo_title: combo_title = "未分类"

        # =========================================================
        # 【核心修正】构造 向量化文本 (Vector Text)
        # 逻辑：必须包含 组合标题 + 换行 + 纯内容
        # =========================================================
        vector_text = f"{combo_title}：\n{raw_content}"

        # 4. 构造 Metadata (存入数据库)
        final_metadata = {
            "来源文件": source,
            "组合标题": combo_title,  # 确保这里存的是短标题
            "完整路径": full_path_str,  # 完整路径也存着备查
            "片段内容": raw_content,  # 纯内容存一份，方便前端回显编辑
            "字数": len(raw_content),
            **l_levels  # L1-L8 展开
        }

        # 5. 向量化
        # 注意：这里使用的是 vector_text (标题+内容)，而不是 raw_content
        emb = call_ai_emb(vector_text, dimensions=EMBEDDING_DIM)
        if not emb: return {"status": "error", "msg": "向量化失败"}

        # 6. 执行数据库更新
        # documents=[vector_text] -> 确保向量库里的主文档是 "标题+内容"
        if req.doc_id:
            col.update(
                ids=[req.doc_id],
                documents=[vector_text],  # 更新 Document 为组合文本
                embeddings=[emb],  # 更新 向量
                metadatas=[final_metadata]  # 更新 元数据
            )
            msg = "更新成功"
        else:
            new_id = str(uuid.uuid4())
            col.add(
                ids=[new_id],
                documents=[vector_text],
                embeddings=[emb],
                metadatas=[final_metadata]
            )
            msg = "新增成功"

        return {"status": "success", "msg": msg}

    except Exception as e:
        return {"status": "error", "msg": str(e)}


def delete_document(req: DeleteRequest):
    client = ChromaAdmin.get_client()
    try:
        col = client.get_collection(req.collection_name)
        col.delete(ids=[req.doc_id])
        return {"status": "success", "msg": "删除成功"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


# ==================== [新增] 数据库概览统计 ====================
def get_database_overview():
    """
    获取数据库概览：包含集合列表、每个集合下的来源文件及对应的条目数
    """
    client = ChromaAdmin.get_client()
    if not client:
        return {"status": "error", "msg": "DB未连接"}

    try:
        collections = client.list_collections()
        overview_data = []

        for col in collections:
            # 只获取 metadatas 以提高速度
            try:
                data = col.get(include=['metadatas'])
                metadatas = data['metadatas']
                total_count = len(metadatas)
            except Exception as e:
                # 防止某个集合损坏导致整个接口挂掉
                overview_data.append({
                    "collection_name": col.name,
                    "total_count": -1,
                    "sources": [{"name": f"读取错误: {str(e)}", "count": 0}]
                })
                continue

            if total_count == 0:
                overview_data.append({
                    "collection_name": col.name,
                    "total_count": 0,
                    "sources": []
                })
                continue

            # 统计来源文件
            source_counter = Counter()
            for meta in metadatas:
                if meta:
                    # 尝试获取来源文件字段
                    name = meta.get('来源文件', meta.get('source', ''))
                    if not name or not name.strip():
                        name = "未知来源/未分类"
                    source_counter[name] += 1

            # 排序：数量多的在前
            sources_list = [
                {"name": name, "count": count}
                for name, count in source_counter.most_common()
            ]

            overview_data.append({
                "collection_name": col.name,
                "total_count": total_count,
                "sources": sources_list
            })

        return {"status": "success", "data": overview_data}

    except Exception as e:
        return {"status": "error", "msg": str(e)}