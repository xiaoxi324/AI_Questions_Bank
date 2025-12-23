import sys
import os

# === 路径修复 (新增) ===
# 目的：确保在 /backend/dingchun/ 目录下也能导入项目根目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 向上跳两级: dingchun -> backend -> root
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)
# ======================

from typing import List, Dict
# 引入底层能力
from backend.tools.tools_call_ai import call_ai_rerank_review
# 引入 search_tool 中的核心搜索和配置获取函数
from backend.search.search_tool import ChromaManager, _core_search, get_search_collections
# 引入上下文变量
from backend.tools.global_context import log_queue_ctx


def emit_log(msg: str):
    """
    辅助函数：既打印到控制台，又推送到前端流
    """
    print(f"[Server Log] {msg}")
    q = log_queue_ctx.get()
    if q:
        q.put(f"LOG: {msg}")


# ==================== Agent 工具接口 (优化版) ====================

def rag_search_tool(search_requests: List[Dict[str, str]]) -> str:
    """
    【Agent专用】批量精准语义检索工具。
    参数简化：接收完整查询句 (query) 和 辅助重排实体 (rerank_entity)。
    """
    final_context = ""

    # 1. 获取检索范围配置
    target_cols = get_search_collections()
    task_count = len(search_requests)
    emit_log(f"🤖 [RAG] 收到 {task_count} 个检索请求...")

    if not target_cols:
        err = "【系统警告】未配置检索集合，请检查配置。"
        emit_log(f"❌ {err}")
        return err

    if not ChromaManager.get_client():
        err = "【系统错误】无法连接至向量数据库。"
        emit_log(f"❌ {err}")
        return err

    # -------------------------------------------------------
    # Phase 1: 向量召回 (串行处理)
    # -------------------------------------------------------
    pending_rerank_tasks = []
    RECALL_K = 15

    for i, req in enumerate(search_requests):
        # === [修改点] 参数简化与明确 ===
        # 1. query: 完整的自然语言搜索句 (例如 "地西泮的适应证是什么？")
        q_text = req.get("query", "")

        # 2. rerank_entity: 辅助重排的实体 (例如 "适应证" 或 "地西泮")
        # Agent 只需要传这一个词，告诉 Rerank 模型重点看什么
        r_entity = req.get("rerank_entity", "")

        # 构造日志描述
        log_desc = f"'{q_text[:20]}...'"
        if r_entity:
            log_desc += f" (辅助: {r_entity})"

        emit_log(f"🔍 [Step 1] ({i + 1}/{task_count}) 检索: {log_desc}")

        try:
            # 核心检索：直接用完整的 q_text 去查
            raw_candidates = _core_search(query_text=q_text, top_k=RECALL_K)

            if raw_candidates:
                processed_candidates = []
                for cand in raw_candidates:
                    meta = cand.get('metadata', {}) or {}
                    content = cand.get('content', '')

                    # 构造重排文本 (标题 + 内容)
                    combo_title = meta.get('组合标题', '')
                    if combo_title:
                        vec_text = f"{combo_title}：\n{content}"
                    else:
                        vec_text = content
                    cand['vector_text'] = vec_text

                    # 构造面包屑路径 (L1-L8)
                    display_path = meta.get('完整路径', '')
                    if not display_path:
                        parts = []
                        for lvl in range(1, 9):
                            val = meta.get(f"L{lvl}")
                            if val and str(val).strip():
                                parts.append(str(val).strip())
                        display_path = " > ".join(parts)

                    if not display_path:
                        display_path = meta.get('来源文件', '未知来源')

                    cand['display_path'] = display_path
                    processed_candidates.append(cand)

                cand_len = len(processed_candidates)
                emit_log(f"      ✅ 初筛命中: {cand_len} 条记录")

                pending_rerank_tasks.append({
                    "req": req,
                    "candidates": processed_candidates,
                    "q_text": q_text,
                    "r_entity": r_entity
                })
            else:
                emit_log(f"      ⚠️ 未找到相关内容")

        except Exception as e:
            emit_log(f"      ❌ 检索异常: {e}")

    # -------------------------------------------------------
    # Phase 2: 语义重排
    # -------------------------------------------------------
    if pending_rerank_tasks:
        emit_log(f"⚖️ [Step 2] 正在进行语义重排 (Rerank)...")

    FINAL_TOP_N = 3

    for task in pending_rerank_tasks:
        candidates = task['candidates']
        q_text = task['q_text']
        r_entity = task['r_entity']

        if not candidates: continue

        final_results = []

        if len(candidates) > 1:
            rerank_inputs = [c['vector_text'] for c in candidates]

            # === [修改点] 重排参数 ===
            # 将 rerank_entity 作为 target_subject 传给模型
            # 如果 Agent 没传 rerank_entity，就传 query 本身作为兜底
            target_subject = r_entity if r_entity else q_text

            rerank_scores = call_ai_rerank_review(
                query=q_text,
                documents=rerank_inputs,
                top_n=FINAL_TOP_N,
                target_subject=target_subject
            )

            for r in rerank_scores:
                for c in candidates:
                    if c['vector_text'] == r['text']:
                        c_copy = c.copy()
                        c_copy['score'] = r['score']
                        final_results.append(c_copy)
                        break

            if final_results:
                top_score = final_results[0]['score']
                res_count = len(final_results)
                sub_log = f" [关注: {r_entity}]" if r_entity else ""
                emit_log(f"      ->{sub_log} 重排选出 Top {res_count} (最高分: {top_score:.2f})")
        else:
            final_results = candidates[:FINAL_TOP_N]

        # 拼接结果 Context
        if final_results:
            title_desc = f"关于“{q_text}”"
            if r_entity:
                title_desc += f" (重点: {r_entity})"

            final_context += f"=== {title_desc} 参考资料 ===\n"
            for item in final_results:
                content = item['content']
                path_info = item.get('display_path', '未知路径')
                source_col = item.get('source_collection', '默认集合')

                final_context += f"【出处: {path_info} ({source_col})】\n{content}\n----------------\n"
            final_context += "\n"

    # --- 完成 ---
    emit_log("📝 [完成] 资料已生成")
    return final_context


# ==================== 独立测试入口 ====================
if __name__ == "__main__":
    print("🚀 开始测试优化版 rag_search_tool ...")

    # 模拟 Agent 请求：更直观的结构
    mock_requests = [
        {
            "query": "地西泮的适应证是什么？",
            "rerank_entity": "适应证"  # 明确告诉 Rerank 关注“适应证”
        },
        {
            "query": "第一章总则的内容",
            "rerank_entity": "总则"
        }
    ]

    result = rag_search_tool(mock_requests)

    print("\n" + "=" * 50)
    print("📝 最终生成的 Context 内容:")
    print("=" * 50)
    print(result)