import os
from openai import OpenAI
from config import config

# ================= 配置区域 =================
# 修改这里来切换要测试的 AI
# 可选值: "KIMI", "QWEN", "DOUBAO", "GPT", "DEEPSEEK", "GEMINI"
TEST_TARGET = "GEMINI"

# 测试问题
TEST_PROMPT = "你好，请用一句话介绍你自己。"


# ===========================================

def run_test():
    print(f"🚀 开始测试 AI 连接...")
    print(f"🎯 目标模型: {TEST_TARGET}")

    api_key = ""
    base_url = ""
    model_name = ""

    # 1. 根据配置选择参数
    if TEST_TARGET == "KIMI":
        api_key = config.KIMI_API_KEY
        base_url = config.KIMI_API_URL
        model_name = config.KIMI_MODEL

    elif TEST_TARGET == "QWEN":
        api_key = config.DASHSCOPE_API_KEY
        base_url = config.DASHSCOPE_API_URL
        model_name = config.DASHSCOPE_MODEL

    elif TEST_TARGET == "DOUBAO":
        api_key = config.VOLCENGINE_API_KEY
        base_url = config.VOLCENGINE_API_URL
        model_name = config.VOLCENGINE_MODEL

    elif TEST_TARGET == "GPT":
        api_key = config.GPT_API_KEY
        base_url = config.GPT_API_URL
        model_name = config.GPT_MODEL

    elif TEST_TARGET == "DEEPSEEK":
        api_key = config.DEEPSEEK_API_KEY
        base_url = config.DEEPSEEK_API_URL
        model_name = config.DEEPSEEK_MODEL

    elif TEST_TARGET == "GEMINI":
        # Gemini 兼容 OpenAI 协议的调用方式
        api_key = config.GOOGLE_API_KEY
        base_url = config.GOOGLE_API_URL
        model_name = config.GOOGLE_MODEL

    else:
        print(f"❌ 未知的测试目标: {TEST_TARGET}")
        return

    print(f"🔌 连接地址: {base_url}")
    print(f"🧠 模型名称: {model_name}")
    print("-" * 50)

    # 2. 初始化客户端 (标准的 OpenAI SDK 方式)
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )

        # 3. 发起请求
        print("🤖 发送请求中...")
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": TEST_PROMPT}
            ],
            temperature=0.7
        )

        # 4. 获取结果
        content = response.choices[0].message.content
        print("\n✅ 测试成功！AI 回复如下：")
        print("=" * 30)
        print(content)
        print("=" * 30)

    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        print("请检查 config.py 中的 API KEY 和 URL 是否正确。")


if __name__ == "__main__":
    run_test()