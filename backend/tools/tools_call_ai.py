import sys
import os

# === 路径修复 (新增) ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)
# ======================

import json
import re
import requests
from openai import OpenAI
from typing import List, Dict, Union, Generator, Optional
from config import config

# 定义类型别名，方便阅读
HistoryType = List[Dict[str, str]]  # [{"role": "user", "content": "..."}]

def call_ai_chat(
        prompt: str,
        history: Optional[HistoryType] = None,
        ai_type: str = "local",
        stream: bool = False,
        temperature: float = 0.7
) -> Union[str, Generator[str, None, None]]:
    """
    统一 AI 聊天接口，支持本地与线上多模型切换及流式输出。
    """
    history = history or []
    messages = history + [{"role": "user", "content": prompt}]

    # ==========================
    # 场景 A: 本地模型 (使用 requests 调用)
    # ==========================
    if ai_type == "local":
        api_url = config.LOCAL_API_URL_CHAT
        model_name = config.LOCAL_CHAT_MODEL
        headers = {"Content-Type": "application/json"}

        if not api_url or not model_name:
            return "❌ 错误：本地模型配置缺失"

        payload = {
            "model": model_name,
            "messages": messages,  # ✅ 已修复：必须是 "messages"
            "temperature": temperature,
            "stream": stream
        }

        try:
            # ---> 本地流式处理
            if stream:
                response = requests.post(api_url, headers=headers, json=payload, stream=True, timeout=None)
                response.raise_for_status()

                def local_stream_generator():
                    for line in response.iter_lines():
                        if line:
                            line_str = line.decode("utf-8").strip().lstrip("data: ").rstrip(",")
                            if line_str == "[DONE]": break
                            try:
                                json_data = json.loads(line_str)
                                delta = json_data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content: yield content
                            except:
                                continue

                return local_stream_generator()

            # ---> 本地非流式处理
            else:
                response = requests.post(api_url, headers=headers, json=payload, timeout=None)
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]

        except Exception as e:
            return f"❌ 本地模型调用失败: {str(e)}"

    # ==========================
    # 场景 B: 线上模型 (使用 OpenAI SDK 兼容调用)
    # ==========================
    else:
        # 配置映射表
        config_map = {
            "dashscope": (config.DASHSCOPE_API_KEY, config.DASHSCOPE_API_URL, config.DASHSCOPE_MODEL),
            "gpt": (config.GPT_API_KEY, config.GPT_API_URL, config.GPT_MODEL),
            "deepseek": (config.DEEPSEEK_API_KEY, config.DEEPSEEK_API_URL, config.DEEPSEEK_MODEL),
            "volcengine": (config.VOLCENGINE_API_KEY, config.VOLCENGINE_API_URL, config.VOLCENGINE_MODEL),
        }

        if ai_type not in config_map:
            return f"❌ 错误：不支持的 AI 类型 '{ai_type}'"

        api_key, base_url, model_name = config_map[ai_type]

        if not all([api_key, base_url, model_name]):
            return f"❌ 错误：{ai_type} 配置参数不完整"

        try:
            client = OpenAI(api_key=api_key, base_url=base_url)

            # ---> 线上流式处理
            if stream:
                completion = client.chat.completions.create(
                    model=model_name, messages=messages, temperature=temperature, stream=True
                )

                def online_stream_generator():
                    for chunk in completion:
                        content = chunk.choices[0].delta.content
                        if content: yield content

                return online_stream_generator()

            # ---> 线上非流式处理
            else:
                completion = client.chat.completions.create(
                    model=model_name, messages=messages, temperature=temperature, stream=False
                )
                return completion.choices[0].message.content

        except Exception as e:
            return f"❌ 线上模型({ai_type})调用失败: {str(e)}"


def call_ai_emb(texts: Union[str, List[str]], dimensions: Optional[int] = None) -> Union[
    List[float], List[List[float]]]:
    """
    调用本地嵌入模型进行文本向量化。
    """
    api_url = config.LOCAL_API_URL_EMB
    model_name = config.LOCAL_EMB_MODEL

    if not api_url or not model_name:
        print("❌ 配置缺失：LOCAL_API_URL_EMB 或 LOCAL_EMB_MODEL 未设置")
        return []

    # 统一转为列表处理
    input_texts = [texts] if isinstance(texts, str) else texts

    payload = {
        "model": model_name,
        "input": input_texts
    }
    if dimensions:
        payload["dimensions"] = dimensions

    try:
        response = requests.post(
            api_url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()

        # 提取向量数据
        embeddings = [item["embedding"] for item in result["data"]]

        # 根据输入类型还原返回格式
        return embeddings[0] if isinstance(texts, str) else embeddings

    except Exception as e:
        print(f"❌ 向量化调用失败: {str(e)}")
        return []

def call_ai_rerank_review(query: str, documents: List[str], top_n: int = 3, target_subject: str = None) -> List[Dict]:
    """
    【审题专用】重排序函数
    """
    api_url = config.LOCAL_API_URL_CHAT
    model_name = config.LOCAL_RERANK_MODEL
    headers = {"Content-Type": "application/json"}

    if not api_url or not model_name or not documents:
        return []

    system_prompt = f"""
    你是考试题目校验专家。请判断以下 {len(documents)} 个药典片段中，哪些最能验证查询语句（题干或选项）的正确性。
    请打分（0-10分）。
    输出格式：仅返回JSON数组：[{{"index": 0, "score": 9.5}}, ...]
    """

    payload = {
        "model": model_name,
        "messages": [  # ✅ 已修复：必须是 "messages"
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": f"查询验证点：{query}\n待验证片段列表：{documents}"}
        ],
        "temperature": 0.0,
        "stream": False
    }

    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=None)
        response.raise_for_status()
        raw_content = response.json()["choices"][0]["message"]["content"]

        clean_content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()
        json_match = re.search(r"```json\s*(\[.*?\])\s*```", clean_content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            start_idx = clean_content.find('[')
            end_idx = clean_content.rfind(']')
            if start_idx != -1 and end_idx != -1:
                json_str = clean_content[start_idx: end_idx + 1]
            else:
                return []

        scores: List[Dict] = json.loads(json_str)

        results = []
        scored_indices = set()

        for item in scores:
            idx = item.get("index")
            raw_score = float(item.get("score", 0.0))

            if isinstance(idx, int) and 0 <= idx < len(documents):
                doc_text = documents[idx]
                final_score = raw_score

                if target_subject:
                    drug_match = re.search(r"药物：(.*?)(?:\[|\||\s)", doc_text)

                    if drug_match:
                        doc_drug = drug_match.group(1).strip()
                        if doc_drug and target_subject not in doc_drug and doc_drug not in target_subject:
                            final_score = raw_score * 0.01

                results.append({"text": doc_text, "score": final_score, "index": idx})
                scored_indices.add(idx)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_n]

    except Exception as e:
        print(f"❌ 审题Rerank异常: {str(e)}")
        return [{"text": doc, "score": 0.0, "index": i} for i, doc in enumerate(documents[:top_n])]