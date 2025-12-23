import sys
import os
import json
from typing import List, Dict, Optional, Union, Any

# === 1. 路径与环境配置 ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

from config import config

# === LangChain 1.0+ 核心组件 ===
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from pydantic import BaseModel, Field

# 导入工具箱 (文件名应为 a_question_tool.py)
from backend.question_agent.a_question_tool import QuestionToolbox

# 初始化工具箱实例
toolbox = QuestionToolbox()


# =================================================================
# 🛠️ 定义 Agent 可用的工具 (Tools)
# =================================================================

@tool
def search_knowledge_tool(keyword: str) -> str:
    """
    [知识检索] 查找医药知识、药典定义、适应症、禁忌症等。
    输入：关键词 (如 "阿司匹林 不良反应")
    """
    results = toolbox.search_knowledge(keyword, top_k=5)
    if not results:
        return "未找到相关药典知识。"
    return "\n\n".join(results)


@tool
def search_case_tool(keyword: str) -> str:
    """
    [案例检索] 查找历史真题案例，用于模仿出题风格。
    输入：关键词 (如 "高血压 案例")
    """
    cases = toolbox.search_similar_cases(keyword, top_k=3)
    if not cases:
        return "未找到相似案例，请自行构建。"

    output = ""
    for i, c in enumerate(cases, 1):
        output += f"--- 参考案例 {i} ---\n{c['content']}\n"
    return output


# =================================================================
# 📋 定义结构化输出 Schema (Pydantic)
# =================================================================

class QuestionSchema(BaseModel):
    """单道题目的结构"""
    stem: str = Field(description="题干内容")
    correct_options: List[str] = Field(description="正确选项列表（单选1个，多选多个）")
    knowledge_ref: str = Field(description="出题依据（引用检索到的知识片段，Agent 需从工具返回中提炼）")


class ExamOutput(BaseModel):
    """最终输出的试题集合"""
    topic: str = Field(description="知识点主题")
    case_content: Optional[str] = Field(description="共用题干/临床案例背景。如果不需要案例，此字段必须为空字符串。",
                                        default="")
    questions: List[QuestionSchema] = Field(description="基于该背景生成的问题列表")


# =================================================================
# 🧠 出题专家 (Questing Agent)
# =================================================================

class QuestingAgent:
    def __init__(self):
        print(f"🧠 [QuestingAgent] 初始化模型: {config.LOCAL_CHAT_MODEL}")

        self.llm = ChatOpenAI(
            base_url=config.LOCAL_OPENAI_URL_CHAT,
            api_key="noneed",
            model=config.LOCAL_CHAT_MODEL,
            temperature=0.7,  # 稍高温度以生成多样化案例
        )

        self.tools = [search_knowledge_tool, search_case_tool]

    def _build_system_prompt(self, params: Dict) -> str:
        """根据前端参数构建 System Prompt"""
        topic = params.get('topic', '未知')

        # === [关键修正] 参数类型转换与题型推断 ===
        # 1. 强制转 int，防止字符串导致的计算或显示异常
        try:
            correct_num = int(params.get('correct_count', 1))
            total_num = int(params.get('total_count', 5))
            q_count = int(params.get('question_count', 1))
        except (ValueError, TypeError):
            # 兜底默认值
            correct_num, total_num, q_count = 1, 5, 1

        has_case = params.get('has_case', False)

        # 2. 自动推断题型 (前端只传了 correct_count，没传 type)
        # 如果正确项 > 1，强制修正为 多选题
        q_type = "单选题" if correct_num == 1 else "多选题"

        # 案例生成的指令
        case_instruction = ""
        if has_case:
            case_instruction = """
            - **必须编写一个临床案例**：包含患者基本信息、主诉、现病史、检查结果。
            - 必须调用 `search_case_tool` 参考真题风格。
            - 案例应隐含有逻辑线索，指向正确答案。
            """
        else:
            case_instruction = "- **不包含案例**：`case_content` 字段必须留空。"

        prompt = f"""你是一名资深的【国家执业药师资格考试】命题专家。
你的任务是基于知识点 "{topic}"，编制 {q_count} 道高质量的试题。

### 1. 命题参数
- 题目数量：{q_count} 道 (如果是案例题，请基于同一个案例背景，编写 {q_count} 道不同的问题，考察不同角度)
- 题型：{q_type}
- 选项要求：总选项数 {total_num} 个，其中正确选项 {correct_num} 个。
- 案例要求：{'需要案例背景' if has_case else '无案例背景'}

### 2. 工作流程
1. **分析**：思考该知识点的核心考查要素。
2. **检索**：
   - 必须调用 `search_knowledge_tool` 获取药典依据。
   - {"如果需要案例，必须调用 `search_case_tool`。" if has_case else "本次不需要调用案例检索工具。"}
3. **生成**：
   {case_instruction}
    - **编题策略（请根据检索到的 RAG 片段特征，选择最合适的一种）**：
         (1) **【逆向映射法】**（适用于适应症/主治）：
             - 逻辑：原文是"药->病"，请反向构建"患者症状->求药"的临床情境。
             - 示例：原文"麻黄发汗解表"，题干应设问"患者恶寒无汗，首选的解表药是？"
             
         (2) **【节点抽离法】**（适用于工艺流程/时序步骤）：
             - 逻辑：原文是"步骤A->B->C"，请描述A和B，询问"下一步操作C是什么"。
             - 示例：原文"水飞法流程..."，题干设问"在完成粗粉碎后，利用粗细粉末悬浮性不同分离杂质的步骤是？"
             
         (3) **【边界测试法】**（适用于剂量/特殊人群/禁忌）：
             - 逻辑：锁定原文中的数字或"禁用/慎用"字眼。
             - 示例：原文"孕妇禁用"，题干设问"下列哪种患者绝对禁止使用该药物？"
             
         (4) **【特征锚定法】**（适用于同类药物辨析）：
             - 逻辑：提取该药物独有的化学基团、代谢特征或特殊副作用作为"题眼"。
             - 示例：原文"只有A药含有氟原子"，题干设问"结构中含有氟原子，半衰期较长的药物是？"
             
         (5) **【逻辑归因法】**（适用于药物相互作用/不良反应）：
             - 逻辑：描述一个用药事故或治疗失败的后果，询问原因或药物机制。
             - 示例：原文"A与B合用导致中毒"，题干设问"患者使用B药后中毒，追问病史发现其合用了？"
   - 编写题干（Stem）。(必须基于RAG检索到的内容，可以基于一个或多个片段，优先采用**原文表述**)
   - 编写正确选项(*必须是RAG检索结果中明确的结论)（Correct Options）。
   **注意：你只需要提供正确选项，干扰选项将由下一位专家生成。**
   
### 禁止要求
- 无RAG检索结果时，不得生成任何题目；
- 不得脱离检索内容设计题干或正确答案；
- 禁止编造知识库来源或原文内容。

请一步步思考，合理使用工具。
"""
        return prompt

    def generate_stream(self, params: Dict):
        """
        流式生成入口
        Yields: 格式化的日志信息
        """
        system_prompt = self._build_system_prompt(params)
        user_input = f"请开始为知识点【{params.get('topic')}】出题。"

        # === 核心：使用 create_agent + ToolStrategy ===
        agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=system_prompt,
            response_format=ToolStrategy(ExamOutput)  # 强制绑定 Pydantic Schema
        )

        # 封装为 LangChain Message 格式
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_input)]

        # 记录已处理的消息ID，防止流式输出重复
        processed_ids = set()

        try:
            # stream_mode="values" 返回当前状态下的所有消息列表
            for event in agent.stream({"messages": messages}, stream_mode="values"):

                messages = event.get("messages", [])
                if not messages: continue

                # 获取最新一条消息
                latest_msg = messages[-1]

                # 去重逻辑
                if hasattr(latest_msg, 'id') and latest_msg.id in processed_ids:
                    continue
                if hasattr(latest_msg, 'id'):
                    processed_ids.add(latest_msg.id)

                # -------------------------------------------------
                # 1. 处理 AI 思考 / 工具调用请求 (AIMessage)
                # -------------------------------------------------
                if isinstance(latest_msg, AIMessage):
                    # A. 决定调用工具
                    if latest_msg.tool_calls:
                        for tc in latest_msg.tool_calls:
                            yield {"type": "process", "content": f"\n🧠 **Agent 思考**: 我需要使用工具 `{tc['name']}`\n"}
                            args_str = json.dumps(tc['args'], ensure_ascii=False)
                            yield {"type": "process", "content": f"   👉 参数: {args_str}\n"}

                    # B. 普通思考内容 (如有)
                    elif latest_msg.content and not latest_msg.tool_calls:
                        # 仅打印非最终 JSON 的思考过程
                        if not (latest_msg.content.strip().startswith("{") and "questions" in latest_msg.content):
                            yield {"type": "process", "content": f"💭 **Agent**: {latest_msg.content}\n"}

                # -------------------------------------------------
                # 2. 处理 工具执行结果 (ToolMessage)
                # -------------------------------------------------
                elif isinstance(latest_msg, ToolMessage):
                    content_preview = latest_msg.content[:100].replace('\n', ' ') + "..."
                    yield {"type": "process", "content": f"📚 **工具返回**: {content_preview}\n"}

            # -------------------------------------------------
            # 3. 处理最终结构化结果 (Structured Response)
            # -------------------------------------------------
            if "structured_response" in event:
                final_data = event["structured_response"]

                # 兼容 Pydantic V1/V2，转换为 JSON 字符串作为最终输出
                if hasattr(final_data, 'model_dump_json'):
                    json_str = final_data.model_dump_json(indent=2, ensure_ascii=False)
                else:
                    json_str = final_data.json(indent=2, ensure_ascii=False)

                yield {"type": "final_json_string", "content": json_str}

        except Exception as e:
            yield {"type": "error", "content": f"\n❌ **发生错误**: {str(e)}\n"}
            import traceback
            traceback.print_exc()


# ==================== 单元测试 ====================
if __name__ == "__main__":
    agent = QuestingAgent()

    # 测试场景 1: 有案例
    test_params_1 = {
        "topic": "高血压的治疗方式",
        # "type": "案例分析题",  <-- 注意：前端通常不传这个，agent 自己推断
        "correct_count": 1,
        "total_count": 5,
        "has_case": False,
        "question_count": 2
    }

    print("\n========= 测试 1: 生成案例题 =========")
    for chunk in agent.generate_stream(test_params_1):
        # 实时打印到控制台
        if chunk.get("type") == "process":
            print(chunk["content"], end="")
        elif chunk.get("type") == "final_json_string":
            print("\n✅ **生成任务完成** (Structured Output):")
            print(chunk["content"])