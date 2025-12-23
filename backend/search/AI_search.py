# backend/search/AI_search.py
import sys
import os
import re
import json
from openai import OpenAI
from typing import List, Dict, Any

# Ensure project root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

from config import config
from backend.search.search_tool import search_knowledge_structured


def segment_text(text: str) -> List[str]:
    """
    Segment the input text into lines.
    Empty lines are skipped.
    """
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return lines


def get_ai_client():
    ai_model = config.LOCAL_CHAT_MODEL
    client = OpenAI(base_url=config.LOCAL_OPENAI_URL_CHAT, api_key="lm-studio")
    if "kimi" in ai_model.lower():
        client = OpenAI(base_url=config.KIMI_API_URL, api_key=config.KIMI_API_KEY)
    elif "doubao" in ai_model.lower():
        client = OpenAI(base_url=config.VOLCENGINE_API_URL, api_key=config.VOLCENGINE_API_KEY)
    return client, ai_model


def compare_segment_with_knowledge(segment: str, knowledge_fragments: List[Dict]) -> Dict[str, Any]:
    """
    Use AI to compare the segment with retrieved knowledge fragments.
    """
    client, model = get_ai_client()

    # Construct knowledge context string
    knowledge_context = ""
    for i, frag in enumerate(knowledge_fragments):
        knowledge_context += f"【片段{i + 1}】(来源: {frag['source']})\n{frag['content']}\n\n"

    prompt = f"""
    你是一个专业的药学文档审核助手。请对比【待审核文本】与【知识库片段】。

    【待审核文本】
    {segment}

    【知识库片段】
    {knowledge_context}

    请严格按照以下标准判断一致性状态：

    1. **完全一致** (fully_consistent): 
       - 待审核文本的内容与知识库原文表述高度吻合，关键词、数据完全一致。
       - 允许极其轻微的格式差异，但核心陈述必须是原文的复述。

    2. **语义一致** (semantically_consistent): 
       - 待审核文本的表述方式（如句式、概括程度）与原文不同，但表达的**核心含义**是完全正确的。
       - **没有**事实性错误，只是写法不同。这是一个“警告”级别，表示通过但需注意措辞。

    3. **错误** (error): 
       - 待审核文本与知识库内容**冲突**、**矛盾**。
       - 或者待审核文本提及的关键数据/事实在知识库中**完全找不到依据**。

    请以JSON格式输出结果，格式如下：
    {{
        "status": "fully_consistent", // 或 "semantically_consistent" 或 "error"
        "diff_description": "差异简述...",
        "suggestion": "修改建议...", // 如果是完全一致，可留空
        "basis_fragment_index": [1]
    }}
    只输出JSON，不要包含其他内容。
    """

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        content = response.choices[0].message.content
        # Simple cleanup for potential markdown code blocks
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```', '', content).strip()
        result = json.loads(content)
        return result
    except Exception as e:
        return {
            "is_consistent": False,
            "diff_description": f"AI处理出错: {str(e)}",
            "suggestion": "请人工核查",
            "basis_fragment_index": []
        }


def process_text_comparison(text: str):
    """
    流式处理：每处理完一段，就 yield 一次结果
    """
    segments = segment_text(text)

    for i, segment in enumerate(segments):
        # 1. 检索
        search_res = search_knowledge_structured(query_main=segment)
        top_fragments = search_res[:3] if search_res else []

        # 2. AI 对比
        comparison = compare_segment_with_knowledge(segment, top_fragments)

        # 3. 构造单条结果对象
        result_item = {
            "index": i + 1,  # 加上序号方便前端排序
            "segment_content": segment,
            "retrieved_fragments": top_fragments,
            "comparison_result": comparison
        }

        # 4. 【关键】使用 yield 逐步返回数据，并用换行符分隔（NDJSON格式）
        # ensure_ascii=False 确保中文不乱码
        yield json.dumps(result_item, ensure_ascii=False) + "\n"


def test_comparison():
    test_text = "阿莫西林主要用于治疗敏感菌引起的感染。对青霉素过敏者禁用。"
    print(f"🧪 测试文本: {test_text}")
    res = process_text_comparison(test_text)
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    test_comparison()