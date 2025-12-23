import sys
import os

# === 路径修复 (新增) ===
# 目的：确保在 /backend/search/ 目录下也能导入项目根目录的 config.py 和 backend.tools
current_dir = os.path.dirname(os.path.abspath(__file__))
# 向上跳两级: search -> backend -> root
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)
# ======================

import json
import chromadb
from typing import List, Dict, Any
from pydantic import BaseModel
from config import config

# [修改导入] 指向新位置 backend.tools
from backend.tools.tools_call_ai import call_ai_emb
from backend.tools.tools_sql_connect import db


# ==================== 模型定义 ====================
class SearchToolRequest(BaseModel):
    keyword: str


class KnowledgeUpdateRequest(BaseModel):
    id: str
    content: str


# ==================== 基础配置 ====================
DB_PATH = getattr(config, "VECTOR_DB_PATH_MEDIC", "G:/KnowledgeBase/vectorizer_medic")
EMBEDDING_DIM = getattr(config, "EMBEDDING_DIM", 4096)


# ==================== 辅助函数 ====================
def get_search_collections() -> List[str]:
    try:
        sql = "SELECT config_value FROM system_config WHERE config_key = 'search_collections'"
        res = db.execute_query(sql, fetch_one=True)
        if res and res['config_value']:
            return json.loads(res['config_value'])
    except Exception as e:
        print(f"⚠️ 读取配置失败: {e}")

    # [修改点1] 默认值改为新的集合名，防止数据库没配置时出错
    return ["Pharmacopoeia_Official"]


class ChromaManager:
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

    @classmethod
    def get_collection(cls, name: str):
        client = cls.get_client()
        return client.get_collection(name=name) if client else None


def _core_search(query_text: str, top_k: int = 10) -> List[Dict]:
    """底层通用检索"""
    target_cols = get_search_collections()
    if not target_cols: return []

    query_emb = call_ai_emb(query_text, dimensions=EMBEDDING_DIM)
    if not query_emb: return []

    all_candidates = []
    for col_name in target_cols:
        col = ChromaManager.get_collection(col_name)
        if not col: continue
        try:
            results = col.query(
                query_embeddings=[query_emb],
                n_results=top_k,
                include=["metadatas", "documents", "distances"]
            )
            if not results['metadatas'] or not results['metadatas'][0]: continue

            for i in range(len(results['metadatas'][0])):
                score = 1 - results['distances'][0][i]
                all_candidates.append({
                    "id": results['ids'][0][i],
                    "content": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i],
                    "raw_score": score,
                    "source_collection": col_name,
                    # 保留 vector_text 用于后续重排
                    "vector_text": results['documents'][0][i]
                })
        except:
            continue

    all_candidates.sort(key=lambda x: x['raw_score'], reverse=True)
    return all_candidates[:top_k]


# ==================== 业务逻辑 (已通用化) ====================

def search_knowledge_structured(query_main: str, query_sub: str = None) -> List[Dict[str, Any]]:
    """
    【通用知识库检索】
    """
    full_query = f"{query_main} {query_sub}" if query_sub else query_main
    print(f"🔎 [RAG] 通用检索: {full_query}")

    raw_results = _core_search(query_text=full_query, top_k=20)

    structured_output = []
    for item in raw_results:
        meta = item['metadata']
        content = item['content']
        score = item['raw_score']

        # === 动态权重优化 ===
        boost = 0.0
        if query_main and query_main in content: boost += 0.2
        if query_sub and query_sub in content: boost += 0.1
        final_score = score + boost

        # === L1-L8 路径构建 (无需修改，这部分逻辑是通用的) ===
        hierarchy_parts = []
        last_valid_node = "未命名节点"

        for i in range(1, 9):
            val = meta.get(f"L{i}")
            if val and str(val).strip():
                hierarchy_parts.append(str(val).strip())
                last_valid_node = str(val).strip()

        path_str = "/".join(hierarchy_parts)

        # 标题策略
        title = meta.get("组合标题")
        if not title:
            title = last_valid_node

        structured_output.append({
            "id": item['id'],
            "source": f"{meta.get('来源文件', 'Base')} | {title}",
            "path": path_str,
            "content": content,
            "raw_score": final_score,
            "score": f"{min(final_score, 0.99):.2%}",
            "_meta_hierarchy": hierarchy_parts
        })

    structured_output.sort(key=lambda x: x['raw_score'], reverse=True)
    return structured_output


def handle_tool_search(req: SearchToolRequest):
    try:
        parts = req.keyword.strip().split(maxsplit=1)
        if not parts: return {"status": "success", "data": []}

        q_main = parts[0]
        q_sub = parts[1] if len(parts) > 1 else None

        results = search_knowledge_structured(query_main=q_main, query_sub=q_sub)
        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


def update_knowledge_record(doc_id: str, new_content: str) -> bool:
    """
    更新记录：确保格式与入库时保持一致 (标题 + 内容)
    """
    target_cols = get_search_collections()
    if not target_cols: return False

    updated_any = False
    for col_name in target_cols:
        col = ChromaManager.get_collection(col_name)
        if not col: continue
        try:
            # 1. 先查出原始元数据（为了获取标题）
            existing = col.get(ids=[doc_id], include=["metadatas"])
            if not existing or not existing['ids']:
                continue

            # [修改点2] 保持向量文本格式一致性
            current_meta = existing['metadatas'][0]
            combo_title = current_meta.get("组合标题", "")

            # 重新拼接向量文本
            if combo_title:
                new_vector_text = f"{combo_title}：\n{new_content}"
            else:
                new_vector_text = new_content

            # 向量化
            new_emb = call_ai_emb(new_vector_text, dimensions=EMBEDDING_DIM)
            if not new_emb: return False

            print(f"🔄 更新集合 [{col_name}] ID={doc_id}")

            # 更新 Documents, Embeddings, 顺便更新字数统计
            current_meta["字数"] = len(new_content)
            current_meta["片段内容"] = new_content  # 也可以选择同步更新元数据里的内容副本

            col.update(
                ids=[doc_id],
                documents=[new_vector_text],  # 这里存入的是拼接后的文本
                embeddings=[new_emb],
                metadatas=[current_meta]
            )
            updated_any = True
            break
        except Exception as e:
            print(f"❌ 更新失败: {e}")
            continue

    return updated_any


def handle_tool_update(req: KnowledgeUpdateRequest):
    try:
        success = update_knowledge_record(req.id, req.content)
        return {"status": "success", "msg": "更新成功"} if success else {"status": "error", "msg": "失败"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


def detailed_read_only_test(test_keyword: str = "禁忌"):
    """
    【只读】详细检索测试
    """
    print("\n" + "=" * 60)
    print(f"🧪 开始只读测试 | 关键词: [{test_keyword}]")
    print("=" * 60)

    # 1. 检查配置
    target_collections = get_search_collections()
    print(f"📋 目标集合: {target_collections}")
    print(f"📂 数据库路径: {DB_PATH}")

    # 2. 检查 AI 连接 (确保向量化正常)
    print("🔌 正在检查 AI 向量化服务...", end="")
    try:
        test_emb = call_ai_emb("test", dimensions=EMBEDDING_DIM)
        if test_emb and len(test_emb) == EMBEDDING_DIM:
            print(" ✅ 连接正常")
        else:
            print(" ❌ 向量化结果为空或维度错误")
            return
    except Exception as e:
        print(f" ❌ 连接失败: {e}")
        return

    # 3. 执行检索
    print(f"🔍 正在执行检索: '{test_keyword}' ...")
    start_time = __import__('time').time()

    # 调用你的业务检索函数
    results = search_knowledge_structured(query_main=test_keyword)

    cost_time = __import__('time').time() - start_time
    print(f"⏱️ 耗时: {cost_time:.4f}s | 找到结果: {len(results)} 条")

    if not results:
        print("⚠️ 未找到相关结果，请尝试更换关键词。")
        return

    # 4. 详细展示前 3 条结果
    print("\n" + "-" * 30 + " 结果详情 " + "-" * 30)

    for i, item in enumerate(results[:3], 1):
        print(f"\n🏷️ [结果 {i}] (匹配度: {item['score']})")
        print(f"🆔 ID: {item['id']}")

        # 重点验证 L1-L8 路径是否解析正确
        print(f"🛤️ 解析路径 (L1-L8): {item['path']}")

        # 验证标题
        source_info = item.get('source', '')
        print(f"📚 来源/标题: {source_info}")

        # 验证内容预览
        content_preview = item['content'].replace('\n', ' ')[:100]
        print(f"📄 内容预览: {content_preview}...")

        # --- 调试用：打印原始元数据 ---
        print(f"🔧 [调试] L层级原始值: {item.get('_meta_hierarchy', [])}")

    print("\n" + "=" * 60)
    print("✅ 测试结束")
    print("=" * 60)


if __name__ == "__main__":
    detailed_read_only_test("失眠")