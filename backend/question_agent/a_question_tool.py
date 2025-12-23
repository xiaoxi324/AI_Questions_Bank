import sys
import os
import json
import chromadb
import threading
from typing import List, Dict, Any, Union

# === 1. 路径与环境配置 ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入配置和工具
from config import config
from backend.tools.tools_call_ai import call_ai_emb
from backend.tools.tools_sql_connect import db

# [新增] 导入全局上下文变量
from backend.tools.global_context import log_queue_ctx

# === 2. 基础配置 ===
DB_PATH = getattr(config, "VECTOR_DB_PATH_MEDIC", "G:/KnowledgeBase/vectorizer_medic")
EMBEDDING_DIM = getattr(config, "EMBEDDING_DIM", 4096)
CASE_COLLECTION_NAME = "Case_Question"


class QuestionToolbox:
    def __init__(self):
        self.client = None
        self._init_chroma()
        self.lock = threading.Lock()

    def _init_chroma(self):
        if not os.path.exists(DB_PATH):
            # print(f"❌ [Toolbox] 向量库路径不存在: {DB_PATH}")
            return
        try:
            self.client = chromadb.PersistentClient(path=DB_PATH)
        except Exception as e:
            print(f"❌ [Toolbox] Chroma连接失败: {e}")

    def _get_active_knowledge_collections(self) -> List[str]:
        """从MySQL读取配置的知识库列表"""
        default = ["Pharmacopoeia_Official"]
        try:
            sql = "SELECT config_value FROM system_config WHERE config_key = 'search_collections'"
            res = db.execute_query(sql, fetch_one=True)
            if res and res['config_value']:
                cols = json.loads(res['config_value'])
                if isinstance(cols, list) and cols:
                    return cols
        except:
            pass
        return default

    # =================================================================
    # 🔍 辅助函数：向全局上下文推送日志
    # =================================================================
    def _push_snippet_to_context(self, title: str, content: str, score: float):
        """
        尝试将检索片段推送到当前上下文的日志队列中
        """
        q = log_queue_ctx.get()  # 获取当前上下文中的队列
        if q:
            # 构造符合前端协议的数据包 type: snippet
            log_data = {
                "type": "snippet",
                "content": f"📌 **{title}** (相似度: {score:.4f})\n{content}\n{'-' * 40}\n"
            }
            # 放入队列，非阻塞
            q.put(log_data)
            print(f"\n[SNIPPET PUSHED] {title}")

    # =================================================================
    # 🛠️ 工具 1: 知识检索
    # =================================================================
    def search_knowledge(self, query: str, top_k: int = 5) -> List[str]:
        if not self.client: return []

        with self.lock:
            vec = call_ai_emb(query, dimensions=EMBEDDING_DIM)
        if not vec: return []

        target_cols = self._get_active_knowledge_collections()
        all_results = []

        for col_name in target_cols:
            try:
                col = self.client.get_collection(col_name)
                res = col.query(query_embeddings=[vec], n_results=top_k,
                                include=["documents", "metadatas", "distances"])
                if res['documents'] and res['documents'][0]:
                    for i in range(len(res['documents'][0])):
                        score = 1 - res['distances'][0][i]
                        item = {
                            "score": score,
                            "content": res['documents'][0][i],
                            "metadata": res['metadatas'][0][i],
                            "collection": col_name
                        }
                        all_results.append(item)
            except:
                continue

        all_results.sort(key=lambda x: x['score'], reverse=True)
        final_list = all_results[:top_k]

        formatted_output = []

        # 🚀 [推送日志]
        q = log_queue_ctx.get()
        if q: q.put({"type": "snippet", "content": f"\n🔍 **正在检索知识**: {query}\n"})

        for i, item in enumerate(final_list):
            source = item['metadata'].get('组合标题', item['metadata'].get('来源文件', '未知来源'))
            content_full = item['content'].strip()

            self._push_snippet_to_context(f"知识来源: {source}", content_full, item['score'])

            text_block = f"【来源：{source}】\n{content_full}"
            formatted_output.append(text_block)

        return formatted_output

    # =================================================================
    # 🛠️ 工具 2: 案例检索
    # =================================================================
    def search_similar_cases(self, query: str, top_k: int = 3) -> List[Dict]:
        if not self.client: return []

        with self.lock:
            vec = call_ai_emb(query, dimensions=EMBEDDING_DIM)
        if not vec: return []

        try:
            col = self.client.get_collection(CASE_COLLECTION_NAME)
            res = col.query(query_embeddings=[vec], n_results=top_k, include=["documents", "metadatas", "distances"])
        except:
            return []

        formatted_cases = []

        # 🚀 [推送日志]
        q = log_queue_ctx.get()
        if q: q.put({"type": "snippet", "content": f"\n💊 **正在检索案例**: {query}\n"})

        if res['documents'] and res['documents'][0]:
            for i in range(len(res['documents'][0])):
                content_full = res['documents'][0][i].strip()
                meta = res['metadatas'][0][i]
                score = 1 - res['distances'][0][i]

                db_ids_str = str(meta.get('db_ids', ''))
                id_list = db_ids_str.split(',') if db_ids_str else []

                self._push_snippet_to_context(f"参考案例 (ID:{db_ids_str})", content_full, score)

                case_obj = {
                    "content": content_full,
                    "question_ids": id_list,
                    "score": score
                }
                formatted_cases.append(case_obj)

        return formatted_cases

    # =================================================================
    # 🛠️ 工具 3: 题目详情检索 (已修正支持 A-L)
    # =================================================================
    def get_full_question_detail(self, question_id: Union[str, int]) -> Dict:
        """
        [工具3] 根据 MySQL ID 获取题目最详细的结构化数据
        """
        if not question_id: return {}

        sql = """
        SELECT * FROM case_question WHERE question_id = %s
        """
        try:
            row = db.execute_query(sql, (question_id,), fetch_one=True)
            if row:
                options = {}
                # ✅ [修正] 扩展到 12 个选项 (A - L)
                full_options = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l']
                for k in full_options:
                    key = f'option_{k}'
                    if row.get(key):
                        options[k.upper()] = row[key]

                return {
                    "id": row['question_id'],
                    "type": row['question_type'],
                    "case": row['case_content'],
                    "stem": row['stem'],
                    "options": options,
                    "answer": row['answer'],
                    "analysis": row['analysis']
                }
        except Exception as e:
            print(f"❌ SQL查询失败: {e}")

        return {}