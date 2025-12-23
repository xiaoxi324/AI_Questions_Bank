# === 路径修复 (确保直接运行不报错) ===
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)
# ====================================

import re
from typing import List, Dict
from langchain.tools import tool
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langchain_openai import ChatOpenAI
# 【恢复】使用你原始的引用
from langchain.agents import create_agent
from config import config

# === 导入路径更新 ===
from backend.tools.tools_sql_connect import db
from backend.dingchun.dingchun_tool_RAG import rag_search_tool as core_rag_search


# ==========================================
# 1. 定义 LangChain Tool
# ==========================================
@tool
def rag_retrieval_tool(search_requests: List[Dict[str, str]]) -> str:
    """
    [RAG核心工具] 批量知识库检索。
    当需要验证医药知识、法律法规或查询事实时使用。

    参数 `search_requests` 是一个字典列表，每个字典包含以下 Key：
    - "query": (必填) 完整的自然语言查询短句，例如 "阿司匹林的禁忌证"。
    - "rerank_entity": (可选) 辅助重排的实体关键词，例如 "禁忌证" 或 "阿司匹林"。
    """
    # 直接调用修改后的核心工具
    return core_rag_search(search_requests)


# ==========================================
# 2. 定义 Agent 类
# ==========================================
class ReviewAgentLocal:
    def __init__(self):
        print(f"🧠 [Local] 初始化本地模型: {config.LOCAL_CHAT_MODEL} ...")

        self.llm = ChatOpenAI(
            base_url=config.LOCAL_OPENAI_URL_CHAT,
            api_key="noneed",
            model=config.LOCAL_CHAT_MODEL,
            temperature=0,
        )

        self.prompt = config.total_prommpt

        # 【恢复】保持你原始的 Agent 构造方式
        self.agent = create_agent(
            self.llm,
            tools=[rag_retrieval_tool],
            system_prompt=self.prompt
        )

    def review_and_save(self, question_id: int) -> Dict:
        sql = "SELECT * FROM pharmacist_questions WHERE question_id = %s"
        q = db.execute_query(sql, (question_id,), fetch_one=True)
        if not q:
            return {"status": "error", "msg": f"题目 ID {question_id} 不存在"}

        # === 【修改点1】扩展选项循环范围 (a -> l) ===
        # 你的数据库定义了 option_a 到 option_l，必须全部遍历
        opts = ""
        valid_options = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l']
        for c in valid_options:
            val = q.get(f'option_{c}')
            # 只有当数据库里有值时才拼接
            if val and str(val).strip():
                opts += f"{c.upper()}.{val}\n"

        # === 【修改点2】拼接案例内容 (Case Content) ===
        case_info = ""
        if q.get('case_content') and str(q['case_content']).strip():
            case_info = f"【共用题干/案例背景】\n{q['case_content']}\n\n"

        # 构造完整的 Prompt 输入
        full_text = (
            f"请校验以下题目：\n"
            f"{case_info}"  # 插入案例
            f"【问题】{q['stem']}\n"
            f"【选项】\n{opts}\n"
            f"【给定答案】{q['answer']}\n"
            f"【给定解析】{q['analysis']}"
        )

        rag_context_extracted = ""
        try:
            print(f"🤖 [Local] 正在思考题目 ID: {question_id} ...")

            # 【恢复】保持你原始的 invoke 调用方式
            res = self.agent.invoke({"messages": [HumanMessage(content=full_text)]})

            # 【恢复】保持你原始的输出获取逻辑
            messages = res.get("messages", [])

            # 如果有消息列表，遍历找工具调用记录
            for msg in messages:
                if isinstance(msg, ToolMessage):
                    rag_context_extracted += f"--- 检索记录 ---\n{msg.content}\n\n"

            # 获取最终回复内容
            if "output" in res:
                raw_content = res["output"]
            elif messages and isinstance(messages[-1], AIMessage):
                raw_content = messages[-1].content
            else:
                print(f"⚠️ [Debug] LangChain 返回结果 keys: {res.keys()}")
                raw_content = str(res)

        except Exception as e:
            print(f"❌ [Local] Agent 执行失败: {e}")
            return {"status": "error", "msg": str(e)}

        clean_content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()

        if "【题目是否正确】正确" in clean_content:
            review_status = "通过"
        elif "【题目是否正确】错误" in clean_content:
            review_status = "驳回"
        else:
            review_status = "需人工确认"

        print(f"💾 [Local] 正在保存审核结果...")

        insert_sql = """
            INSERT INTO question_review_details 
            (question_id, ai_name, review_result, review_content, rag_index, review_time) 
            VALUES (%s, %s, %s, %s, %s, NOW())
        """

        affected = db.execute_update(insert_sql, (
            question_id,
            f"定春(L)",
            review_status,
            clean_content,
            rag_context_extracted
        ))

        if not affected:
            print("❌ 数据库写入返回 None，请检查上方 SQL 错误日志")

        return {
            "status": "success",
            "review_result": review_status,
            "review_content": clean_content,
            "rag_context": rag_context_extracted
        }


# ================= 测试入口 =================
if __name__ == "__main__":
    print("\n🧪 正在进行 Local Core 单元测试...")
    TEST_ID = 26
    agent = ReviewAgentLocal()
    print(f"▶️  开始对 ID={TEST_ID} 进行审题...")
    result = agent.review_and_save(TEST_ID)

    print("\n" + "=" * 50)
    if result['status'] == 'success':
        print(f"✅ 测试通过！")
        print(f"📊 结论: {result['review_result']}")
        print("-" * 30)
        if result['rag_context']:
            print(f"📝 [RAG检索记录预览]:\n{result['rag_context'][:200]}...\n")
        print("📝 [AI回复预览]:")
        print(result['review_content'][:200] + "...")
    else:
        print(f"❌ 测试失败: {result['msg']}")