import sys
import os
import json
import random
import string
from typing import List, Dict, Any, Literal, Optional, Generator

# === 1. 路径与环境配置 ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

from config import config
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field

# 选项的字母列表 (A, B, C... L)
OPTION_KEYS = [string.ascii_uppercase[i] for i in range(12)]


# =================================================================
# 📋 定义最终输出 Schema (匹配数据库字段)
# =================================================================

class FinalQuestionSchema(BaseModel):
    """
    最终输出结构，包含审核状态和数据库所需字段
    """
    # 审核状态字段
    verification_status: Literal["PASS", "FAIL", "NEEDS_REVIEW"] = Field(
        description="审核结论：PASS(通过), FAIL(驳回), NEEDS_REVIEW(需人工确认)。"
    )
    review_comment: str = Field(
        description="审核人意见。如果是FAIL则说明不通过的原因，否则为'题目结构合理，可入库'。"
    )

    # 题目核心字段 (映射到 pharmacist_questions 表)
    question_type: str = Field(description="题目类型，例如 'A型题' 或 '案例分析题'")
    case_content: str = Field(description="案例背景，无案例时必须为空字符串")
    stem: str = Field(description="题目题干")

    # 最终选项列表
    options_final: Dict[str, str] = Field(
        description="最终选项列表，键为选项字母 (A, B, C...)，值为选项内容"
    )

    # 最终答案
    final_answer_key: str = Field(
        description="最终答案键名字符串，例如: 'A', 'B, C', 'E, F, G' (必须是乱序后的选项字母)")

    # 完整解析
    analysis: str = Field(description="详细解析，包含考点、答案依据、干扰项设计逻辑。")
    source: str = Field(description="题目来源，固定为 '智能编题'")


# =================================================================
# ⚖️ 审定专家 (Finalization Agent)
# =================================================================

class FinalizationAgent:
    def __init__(self):
        print(f"🧠 [FinalAgent] 初始化模型 (Auditor Mode)...")
        self.llm = ChatOpenAI(
            base_url=config.LOCAL_OPENAI_URL_CHAT,
            api_key="noneed",
            model=config.LOCAL_CHAT_MODEL,
            temperature=0.01,  # 极低温度，追求稳定
        )
        self.tools = []

    def _build_system_prompt(self, assembled_data: Dict) -> tuple[str, Dict, str]:
        """根据组装好的数据构建审计 Prompt"""

        # 从 Agent B/C 获取的原始数据
        case_content = assembled_data.get('case_content', '')
        stem = assembled_data.get('stem', '未定义题干')
        correct_options = assembled_data.get('correct_options', [])

        # 兼容处理：干扰项可能是字符串列表，也可能是字典列表
        raw_distractors = assembled_data.get('distractors', [])
        distractors = []
        for d in raw_distractors:
            if isinstance(d, dict):
                distractors.append(d.get('content', '无效选项'))
            elif isinstance(d, str):
                distractors.append(d)
            else:
                distractors.append(str(d))

        analysis_overall = assembled_data.get('analysis_overall', '无')

        # 1. 混合选项并确定总数
        all_options = correct_options + distractors

        # 2. Python 负责乱序 (确保 AI 不会重复计算)
        random.shuffle(all_options)

        # 3. 构造最终选项字典 (A, B, C...)
        final_options_dict = {
            OPTION_KEYS[i]: content
            for i, content in enumerate(all_options)
        }

        # 4. 确定最终答案键名字符串
        correct_keys = []
        for correct_content in correct_options:
            for key, content in final_options_dict.items():
                if content == correct_content:
                    correct_keys.append(key)
                    break
        final_answer_key = ", ".join(sorted(correct_keys))

        # 5. 构造 Prompt 输入
        prompt = f"""你是一名【国家执业药师资格考试】的审核专家。你的职责是：
1. **审计**：严格校验题目的**准确性**、**唯一性**和**干扰性**。
2. **格式化**：将所有信息整合进最终的结构。

### 1. 待审核题目信息
- **案例背景 (必须复制到 JSON 中)**: {case_content if case_content else "(无)"} 
- **题干 (Stem)**: {stem}
- **最终选项列表 (已乱序)**: {json.dumps(final_options_dict, ensure_ascii=False)}
- **正确答案内容**: {json.dumps(correct_options, ensure_ascii=False)}
- **参考解析**: {analysis_overall}
- **正确答案键 (系统计算结果)**: {final_answer_key}

### 2. 严谨性校验规则
1. **准确性**：正确选项的内容是否被原始依据支持。
2. **唯一性**：是否存在多个正确答案？（如果有多选，是否正确项都被列出？）
3. **干扰性**：干扰项是否合理且不具备歧义？

### 3. 最终输出要求
- **步骤 1 (Audit)**: 根据校验规则，首先确定 'verification_status'。
- **步骤 2 (Finalize)**: 严格按照 FinalQuestionSchema 格式输出。**特别注意：必须将上方的'案例背景'完整填入 `case_content` 字段，不能留空（除非原本就是空）。**

请使用 JSON 格式输出。
"""
        return prompt, final_options_dict, final_answer_key

    def process_question(self, assembled_data: Dict) -> Generator[Dict, None, None]:
        """
        处理单道组装好的题目，并流式输出结果
        """
        # 0. 准备数据和Prompt
        try:
            sys_prompt, final_options_dict, final_answer_key = self._build_system_prompt(assembled_data)
        except Exception as e:
            yield {"error": f"数据准备失败: {str(e)}"}
            return

        user_input = "请开始执行审核和定稿任务，输出最终的 JSON 结构。"

        # 1. 创建 Agent (无工具)
        agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=sys_prompt,
            response_format=ToolStrategy(FinalQuestionSchema)
        )

        yield {"log": f"📝 **开始审计**: 题目主题 {assembled_data.get('topic')}"}
        yield {"log": f"📏 **系统预计算答案**: {final_answer_key}"}

        # 2. 流式执行
        try:
            # stream_mode="values" 确保我们能拿到最后生成的 Pydantic 对象
            for event in agent.stream({"messages": [HumanMessage(content=user_input)]}, stream_mode="values"):

                messages = event.get("messages", [])
                if messages and isinstance(messages[-1], AIMessage):
                    latest_msg = messages[-1].content
                    # 打印思考过程
                    if latest_msg and not latest_msg.strip().startswith("{"):
                        yield {"thought": latest_msg}

            # 3. 获取最终结果 (从 event 中提取 structured_response)
            if "structured_response" in event:
                final_data: FinalQuestionSchema = event["structured_response"]

                # 4. 构造数据库记录 (映射 option_a 到 option_l)
                db_record = {
                    'question_type': final_data.question_type,
                    'case_content': final_data.case_content,
                    'stem': final_data.stem,
                    'answer': final_data.final_answer_key,
                    'analysis': final_data.analysis,
                    'source': final_data.source
                }

                # 映射 option_a 到 option_l
                for i, key in enumerate(OPTION_KEYS):
                    content = final_options_dict.get(key, None)
                    db_record[f"option_{key.lower()}"] = content

                # 5. 校验 Agent 的答案键是否正确
                if final_data.final_answer_key != final_answer_key:
                    final_data.verification_status = "FAIL"
                    final_data.review_comment = f"答案键不匹配。系统计算={final_answer_key}, Agent返回={final_data.final_answer_key}。"

                yield {
                    "audit_status": final_data.verification_status,
                    "review_comment": final_data.review_comment,
                    "final_data": db_record
                }
            else:
                yield {"error": "Agent D 未返回结构化数据 structured_response"}

        except Exception as e:
            yield {"error": f"Agent 执行失败: {str(e)}"}
            import traceback
            traceback.print_exc()


# ==================== 单元测试 (模拟输入) ====================
if __name__ == "__main__":
    agent = FinalizationAgent()

    # 模拟输入数据
    mock_assembled_data = {
        "topic": "地西泮 中毒",
        "question_type": "A型题",
        "case_content": "患者，男性，55岁，因安眠药过量入院。",
        "stem": "首选的拮抗剂是：",
        "correct_options": ["氟马西尼"],
        "distractors": ["纳洛酮", "碳酸氢钠", "阿托品", "葡萄糖"],
        "analysis_overall": "氟马西尼是苯二氮䓬类拮抗剂。"
    }

    print("\n========= 🧪 开始审计与格式化测试 =========")
    for result in agent.process_question(mock_assembled_data):
        if result.get("error"):
            print(f"❌ ERROR: {result['error']}")
        elif result.get("thought"):
            print(f"💭 {result['thought']}")
        elif result.get("audit_status"):
            print("\n" + "=" * 50)
            print(f"✅ 审计状态: {result['audit_status']}")
            print(json.dumps(result['final_data'], indent=2, ensure_ascii=False))