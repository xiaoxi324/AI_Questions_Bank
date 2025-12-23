import sys
import os
import json
from typing import List, Dict, Optional, Any

# === 1. 路径与环境配置 ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

from config import config

# === LangChain 1.0+ 组件 ===
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from pydantic import BaseModel, Field

# [关键修正] 导入工具箱 (文件名应为 a_question_tool.py)
from backend.question_agent.a_question_tool import QuestionToolbox

# 初始化工具箱
toolbox = QuestionToolbox()


# =================================================================
# 🛠️ 定义干扰项专家专用工具
# =================================================================

@tool
def search_competitor_knowledge(keyword: str) -> str:
    """
    [差异化检索] 用于查找与正确答案相似、易混淆的知识点。
    例如：如果正确答案是"阿司匹林"，你可以搜"布洛芬"、"对乙酰氨基酚"来寻找干扰素材。
    输入：易混淆的关键词。
    """
    # print(f"   😈 [设坑检索] 正在寻找干扰素材: {keyword}")
    results = toolbox.search_knowledge(keyword, top_k=3)
    if not results:
        return "未找到相关对比知识，请基于药学常识构建干扰项。"
    return "\n\n".join(results)


# =================================================================
# 📋 定义结构化输出 Schema
# =================================================================

class DistractorSchema(BaseModel):
    """单个干扰项结构"""
    content: str = Field(description="干扰项的内容")
    trap_analysis: str = Field(description="设计思路：为什么这个选项具有迷惑性？（例如：张冠李戴、数值混淆）")


class DistractionOutput(BaseModel):
    """干扰项生成结果"""
    distractors: List[DistractorSchema] = Field(description="生成的干扰选项列表")
    analysis_overall: str = Field(description="针对整道题的解析（解释正确项为什么对，干扰项为什么错）")


# =================================================================
# 😈 干扰项专家 (Distraction Agent)
# =================================================================

class DistractionAgent:
    def __init__(self):
        print(f"🧠 [DistractionAgent] 初始化模型: {config.LOCAL_CHAT_MODEL} (设坑模式)")

        self.llm = ChatOpenAI(
            base_url=config.LOCAL_OPENAI_URL_CHAT,
            api_key="noneed",
            model=config.LOCAL_CHAT_MODEL,
            temperature=0.8,  # 干扰项需要更高的创造力来"编造"合理的错误
        )

        self.tools = [search_competitor_knowledge]

    def _build_system_prompt(self, context: Dict) -> str:
        """
        构建“设坑”专用 Prompt
        """
        topic = context.get('topic', '未知')
        stem = context.get('stem', '')
        correct_options = context.get('correct_options', [])
        target_count = context.get('distractor_count', 3)  # 需要生成的干扰项数量

        prompt = f"""你是一名【国家执业药师资格考试】的命题组专家，专门负责**编写干扰选项（Distractors）**。
你的目标是设计出{target_count}个**似是而非**、具有高迷惑性的错误选项，考察考生对知识点的精确掌握程度。

### 1. 题目信息
- **核心考点**：{topic}
- **题干**：{stem}
- **正确答案**：{json.dumps(correct_options, ensure_ascii=False)}

### 2. 干扰项设计策略（必须执行）
不要凭空捏造，请调用 `search_competitor_knowledge` 工具去检索**同类药物**或**易混淆概念**的真实属性，然后将其作为干扰项。
推荐策略：
1. **张冠李戴**：搜索同类药物的特性，移花接木。例如：考"阿司匹林"，去搜"对乙酰氨基酚"的副作用作为干扰项。
2. **逻辑反转**：将"适应症"写成"禁忌症"，将"抑制"写成"促进"。
3. **程度偏差**：将"慎用"写成"禁用"，将"常见"写成"罕见"。
4. **数值混淆**：如果涉及剂量，搜索该药物的其他剂型用法进行混淆。

### 3. 工作流程
1. **分析**：分析正确答案的特征，确定易混淆对象（竞品药物）。
2. **检索**：调用工具搜索易混淆对象的属性。
3. **生成**：编写 {target_count} 个干扰选项，并为每个选项注明设计思路。
4. **解析**：最后编写一段完整的试题解析，解释正确项并指出干扰项的错误之处。

### 4. 输出格式
请输出严格的 JSON 格式。
"""
        return prompt

    def generate_stream(self, context: Dict):
        """
        流式生成干扰项
        """
        system_prompt = self._build_system_prompt(context)
        user_input = "请开始编写干扰选项。"

        # 创建 Agent
        agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=system_prompt,
            response_format=ToolStrategy(DistractionOutput)
        )

        print(f"😈 [Agent] 开始设坑: {context.get('topic')}")

        processed_ids = set()

        try:
            for event in agent.stream({"messages": [HumanMessage(content=user_input)]}, stream_mode="values"):

                messages = event.get("messages", [])
                if not messages: continue
                latest_msg = messages[-1]

                if hasattr(latest_msg, 'id') and latest_msg.id in processed_ids:
                    continue
                if hasattr(latest_msg, 'id'):
                    processed_ids.add(latest_msg.id)

                # 1. 思考与工具调用
                if isinstance(latest_msg, AIMessage):
                    if latest_msg.tool_calls:
                        for tc in latest_msg.tool_calls:
                            yield {"type": "process",
                                   "content": f"\n🧠 **Agent 思考**: 找点干扰素材，查询 `{tc['name']}`\n"}
                            yield {"type": "process",
                                   "content": f"   👉 参数: {json.dumps(tc['args'], ensure_ascii=False)}\n"}
                    elif latest_msg.content:
                        if not (latest_msg.content.strip().startswith("{") and "distractors" in latest_msg.content):
                            yield {"type": "process", "content": f"💭 **Agent**: {latest_msg.content}\n"}

                # 2. 工具返回
                elif isinstance(latest_msg, ToolMessage):
                    content_preview = latest_msg.content[:100].replace('\n', ' ') + "..."
                    yield {"type": "process", "content": f"📚 **混淆知识返回**: {content_preview}\n"}

            # 3. 最终结果
            if "structured_response" in event:
                final_data = event["structured_response"]

                # 转换为 JSON 字符串
                if hasattr(final_data, 'model_dump_json'):
                    json_str = final_data.model_dump_json(indent=2, ensure_ascii=False)
                else:
                    json_str = final_data.json(indent=2, ensure_ascii=False)

                # 关键：标记为 final_json_string，供 z_common.py 捕获
                yield {"type": "final_json_string", "content": json_str}

        except Exception as e:
            yield {"type": "error", "content": f"\n❌ **发生错误**: {str(e)}\n"}
            import traceback
            traceback.print_exc()


# ==================== 单元测试 ====================
if __name__ == "__main__":
    agent = DistractionAgent()

    # 模拟从 b_question_agent 传来的数据
    input_context = {
        "topic": "阿司匹林",
        "stem": "患者女性，58岁，因关节疼痛长期服用止痛药，近期出现黑便。关于该药物的作用机制，叙述正确的是",
        "correct_options": ["不可逆抑制环氧酶，减少血栓素A2的合成"],
        "distractor_count": 4  # 需要补全4个干扰项
    }

    print("-------------- 开始流式测试 --------------")
    for chunk in agent.generate_stream(input_context):
        if chunk.get("type") == "process":
            print(chunk["content"], end="")
        elif chunk.get("type") == "final_json_string":
            print("\n✅ **干扰项生成完成**:")
            print(chunk["content"])