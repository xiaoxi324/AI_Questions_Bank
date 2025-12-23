# === 路径修复 (新增) ===
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
# 向上跳两级: dingchun -> backend -> root
root_dir = os.path.dirname(os.path.dirname(current_dir))
if root_dir not in sys.path:
    sys.path.append(root_dir)
# ======================

import json
import re
from typing import Dict, List
from openai import OpenAI
from config import config

# 导入工具模块
from backend.tools.tools_sql_connect import db
# 拼写修正: dingchun -> dingchun
from backend.dingchun.dingchun_tool_RAG import rag_search_tool
from backend.tools.global_context import log_queue_ctx


def emit(msg):
    print(f"[DingChun-Kimi] {msg}")
    q = log_queue_ctx.get()
    if q: q.put(f"LOG: {msg}")


# ✅ 修复类名：改为 ReviewAgentKimi，与 dingchun.py 中的引用保持一致
class ReviewAgentKimi:
    def __init__(self):
        print(f"🔌 [Kimi] 初始化定春(K)核心 (Native SDK)...")

        self.client = OpenAI(
            base_url=config.KIMI_API_URL,
            api_key=config.KIMI_API_KEY,
        )
        self.model = config.KIMI_MODEL
        self.system_prompt = config.total_prommpt

        # 工具 Schema
        self.tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "rag_search_tool",
                    "description": "批量检索药典。当题目涉及具体药物、病症或知识点时，必须调用此工具。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_requests": {
                                "type": "array",
                                "description": "检索请求列表",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "query": {
                                            "type": "string",
                                            "description": "查询短句，如'阿司匹林 不良反应'"
                                        },
                                        "rerank_entity": {
                                            "type": "string",
                                            "description": "辅助重排的实体关键词，如'阿司匹林'"
                                        }
                                    },
                                    "required": ["query"]
                                }
                            }
                        },
                        "required": ["search_requests"]
                    }
                }
            }
        ]

    # ✅ 适配修改：接收字典参数
    def review_question(self, question_data: Dict) -> Dict:
        q_id = question_data['question_id']

        # 拼接选项
        options = ""
        valid_opts = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l']
        for char in valid_opts:
            val = question_data.get(f'option_{char}')
            if val and str(val).strip():
                options += f"{char.upper()}.{val}\n"

        # 拼接案例
        case_info = ""
        if question_data.get('case_content') and str(question_data['case_content']).strip():
            case_info = f"【共用题干/案例背景】\n{question_data['case_content']}\n\n"

        full_text = (
            f"请校验以下题目：\n"
            f"{case_info}"
            f"【题干】{question_data['stem']}\n【选项】\n{options}\n"
            f"【给定答案】{question_data['answer']}\n【给定解析】{question_data['analysis']}"
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": full_text}
        ]

        current_rag_log = ""
        review_result = "需人工确认"
        clean_content = ""

        try:
            emit(f"🤖 [Kimi] 正在思考题目 ID: {q_id} (请求工具)...")

            # Round 1
            resp1 = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools_schema,
                tool_choice={"type": "function", "function": {"name": "rag_search_tool"}},
                temperature=0
            )

            response_message = resp1.choices[0].message
            tool_calls = response_message.tool_calls

            if not tool_calls:
                emit("⚠️ Kimi 未调用工具，直接回答")
            else:
                messages.append(response_message)

                # Round 2
                for tool_call in tool_calls:
                    try:
                        args = json.loads(tool_call.function.arguments)
                        req_list = args.get('search_requests', [])
                        emit(f"🛠️ [Kimi] 正在检索 {len(req_list)} 个知识点...")

                        rag_result = rag_search_tool(req_list)

                        current_rag_log += f"--- 检索请求 ---\n{json.dumps(req_list, ensure_ascii=False)}\n"
                        current_rag_log += f"--- 检索结果 ---\n{rag_result}\n\n"

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.function.name,
                            "content": rag_result
                        })
                    except Exception as te:
                        emit(f"❌ 工具参数解析失败: {te}")

            # Round 3
            emit("🧠 [Kimi] 正在生成最终报告...")
            resp2 = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0
            )
            raw_content = resp2.choices[0].message.content

            clean_content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()

            if "【题目是否正确】正确" in clean_content:
                review_result = "通过"
            elif "【题目是否正确】错误" in clean_content:
                review_result = "驳回"

        except Exception as e:
            emit(f"❌ [Kimi] API 异常: {e}")
            clean_content = f"API Error: {e}"
            review_result = "错误"

        # 5. 存库
        emit(f"💾 [Kimi] 正在保存结果 ({review_result})...")

        # ✅ 修复：必须包含 review_time
        sql = """
            INSERT INTO question_review_details 
            (question_id, ai_name, review_result, review_content, rag_index, review_time) 
            VALUES (%s, %s, %s, %s, %s, NOW())
        """

        try:
            affected = db.execute_update(sql, (
                q_id,
                "定春(K)",
                review_result,
                clean_content,
                current_rag_log
            ))
            if not affected:
                emit("❌ 数据库写入返回 None")
        except Exception as e:
            emit(f"❌ 数据库写入失败: {e}")

        return {
            "status": "success",
            "review_result": review_result,
            "review_content": clean_content,
            "rag_context": current_rag_log
        }


if __name__ == "__main__":
    print("🚀 测试 Kimi Agent...")
    mock_q = {
        "question_id": 26, "stem": "测试", "answer": "A", "analysis": ""
    }
    ReviewAgentKimi().review_question(mock_q)