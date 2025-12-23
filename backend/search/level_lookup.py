import sys
import os
import math
import json
import chromadb

# === 路径修复 ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)
# ======================

from typing import List, Dict, Any
from pydantic import BaseModel

# === 导入依赖 ===
from backend.knowledge.knowledge_tool import ChromaAdmin
from backend.tools.tools_call_ai import call_ai_emb
from backend.tools.tools_sql_connect import db
from config import config

EMBEDDING_DIM = getattr(config, "EMBEDDING_DIM", 4096)


# ==================== 请求模型 ====================
class LevelLookupRequest(BaseModel):
    title_filter: str  # 过滤条件
    search_content: str  # 检索内容


# ==================== 辅助函数 ====================

def get_target_collections() -> List[str]:
    """
    [移植自 search_tool.py] 从 SQL 数据库获取配置的集合列表
    """
    try:
        sql = "SELECT config_value FROM system_config WHERE config_key = 'search_collections'"
        res = db.execute_query(sql, fetch_one=True)
        if res and res['config_value']:
            return json.loads(res['config_value'])
    except Exception as e:
        print(f"⚠️ [LevelLookup] 读取集合配置失败: {e}")

    return ["Pharmacopoeia_Official"]


def calculate_cosine_similarity(vec1: Any, vec2: Any) -> float:
    """
    【修复版】计算余弦相似度
    修复了 NumPy 数组在 if 判断中的 ambiguous 错误
    """
    # 1. 安全检查：显式检查 None
    if vec1 is None or vec2 is None:
        return 0.0

    # 2. 安全检查：检查长度 (无论 list 还是 numpy array 都有 len)
    if len(vec1) == 0 or len(vec2) == 0:
        return 0.0

    # 3. 维度检查
    if len(vec1) != len(vec2):
        return 0.0

    # 4. 计算逻辑
    try:
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm_a = math.sqrt(sum(a * a for a in vec1))
        norm_b = math.sqrt(sum(b * b for b in vec2))

        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)
    except Exception as e:
        print(f"⚠️ 相似度计算数值错误: {e}")
        return 0.0


# ==================== 核心业务逻辑 ====================

def execute_level_lookup(req: LevelLookupRequest) -> Dict[str, Any]:
    """
    执行级标检索
    """
    print(f"🔍 [LevelLookup] 过滤: '{req.title_filter}' | 语义: '{req.search_content}'")

    client = ChromaAdmin.get_client()
    if not client:
        return {"status": "error", "msg": "向量数据库未连接"}

    # 1. 动态获取所有目标集合
    target_cols = get_target_collections()
    if not target_cols:
        return {"status": "error", "msg": "未配置目标集合"}

    # 2. 预先向量化检索词
    query_emb = call_ai_emb(req.search_content, dimensions=EMBEDDING_DIM)
    if not query_emb:
        return {"status": "error", "msg": "AI向量化服务失败"}

    all_results = []
    total_candidates_count = 0

    # 3. 遍历所有集合
    for col_name in target_cols:
        try:
            col = client.get_collection(col_name)
            if not col: continue

            # --- 阶段一：基于标题/路径的硬过滤 ---
            all_data = col.get(include=["metadatas"])
            all_ids = all_data['ids']
            all_metas = all_data['metadatas']

            local_candidate_ids = []
            filter_key = req.title_filter.strip().lower()

            for i, meta in enumerate(all_metas):
                if not meta: continue

                # 匹配逻辑
                is_hit = False
                combo = str(meta.get("组合标题", "")).lower()
                path = str(meta.get("完整路径", "")).lower()

                if filter_key in combo or filter_key in path:
                    is_hit = True
                else:
                    for k in range(1, 9):
                        val = str(meta.get(f"L{k}", "")).lower()
                        if filter_key in val:
                            is_hit = True
                            break

                if is_hit:
                    local_candidate_ids.append(all_ids[i])

            count_local = len(local_candidate_ids)
            total_candidates_count += count_local

            if count_local == 0:
                continue

            # --- 阶段二：语义重排 ---
            target_data = col.get(
                ids=local_candidate_ids,
                include=["embeddings", "documents", "metadatas"]
            )

            for i in range(len(target_data['ids'])):
                doc_emb = target_data['embeddings'][i]

                # [关键] 这里传入的 doc_emb 可能是 numpy 数组，现在 calculate_cosine_similarity 已兼容
                score = calculate_cosine_similarity(query_emb, doc_emb)

                all_results.append({
                    "id": target_data['ids'][i],
                    "content": target_data['documents'][i],
                    "metadata": target_data['metadatas'][i],
                    "source_collection": col_name,
                    "score": score,
                    "score_percent": f"{score:.2%}"
                })

        except Exception as e:
            # 这里的 print 有助于捕获具体是哪个集合报了什么错
            print(f"⚠️ 集合 [{col_name}] 处理出错: {e}")
            continue

    # 4. 全局排序
    all_results.sort(key=lambda x: x['score'], reverse=True)

    # 5. 截取 Top 50
    final_top = all_results[:50]

    return {
        "status": "success",
        "total_candidates_scanned": total_candidates_count,
        "returned_count": len(final_top),
        "data": final_top
    }


# ==================== 测试入口 ====================
if __name__ == "__main__":
    # 简单自测
    test_req = LevelLookupRequest(
        title_filter="感冒",
        search_content="发烧头痛"
    )
    res = execute_level_lookup(test_req)
    print(f"\n✅ 最终状态: {res['status']}")
    print(f"📊 扫描: {res.get('total_candidates_scanned')} | 返回: {res.get('returned_count')}")

    if res.get('data'):
        top = res['data'][0]
        print(f"🥇 TOP1: {top['metadata']['组合标题']} | 分数: {top['score_percent']}")
    else:
        print("⚠️ 未找到匹配结果")