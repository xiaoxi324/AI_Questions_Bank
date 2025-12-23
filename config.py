class Config:
    """核心配置类（合并原.env和Config数据，无需额外加载.env文件）"""

    # ==================== 路径配置 ====================
    # 知识库原始文件存储路径
    KNOWLEDGE_BASE_PATH = "请填入您的实际地址"      # 原始未处理知识库地址
    KNOWLEDGE_BASE_PATH_SEG_ORG = "请填入您的实际地址"    # 知识库原始切分地址
    KNOWLEDGE_BASE_PATH_SEG_AI = "请填入您的实际地址"           # 知识库AI处理切分地址

    # 向量数据库存储路径
    VECTOR_DB_PATH_MEDIC = "请填入您的实际地址"     # 药学数据库地址
    VECTOR_DB_PATH_CASE = ""                                       # 案例位置

    # ==================== 向量数据库基础配置 ====================
    VECTOR_DB_COLLECTION = "Pharmacopoeia"                        # 默认集合名称
    EMBEDDING_DIM = 4096                                        # 嵌入维度（根据模型实际值调整）

    # ==================== 百炼模型配置 ====================
    DASHSCOPE_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DASHSCOPE_API_KEY = "在此填入您的Key"
    DASHSCOPE_MODEL = "qwen3-vl-plus"

    # ==================== KIMI模型配置 ====================
    KIMI_API_URL = "https://api.moonshot.cn/v1"
    KIMI_API_KEY = "在此填入您的Key"
    KIMI_MODEL = "kimi-k2-0905-preview"

    # ==================== 火山引擎模型配置 ====================
    VOLCENGINE_API_URL = "https://ark.cn-beijing.volces.com/api/v3"
    VOLCENGINE_API_KEY = "在此填入您的Key"
    VOLCENGINE_MODEL = "doubao-seed-1-6-251015"

    # ==================== google模型配置 ====================
    GOOGLE_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
    GOOGLE_API_KEY = "在此填入您的Key"
    GOOGLE_MODEL = "gemini-3-pro-preview"

    # ==================== GPT模型配置 ====================
    GPT_API_URL = "https://api.openai.com/v1"
    GPT_API_KEY = "在此填入您的Key"
    GPT_Organization_ID = "在此填入您的ID"
    GPT_MODEL = "gpt-3.5-turbo"

    # ==================== Deepseek模型配置 ====================
    DEEPSEEK_API_URL = "https://api.deepseek.com"
    DEEPSEEK_API_KEY = "在此填入您的Key"
    DEEPSEEK_MODEL = "deepseek-chat"

    # ==================== 本地模型配置 ====================
    LOCAL_OPENAI_URL_CHAT = "http://localhost:6324/v1"                  # 本地LMstudio聊天模型OpenAI兼容地址
    LOCAL_API_URL_CHAT = "http://127.0.0.1:6324/v1/chat/completions"    # 本地LMstudio聊天模型调用地址
    LOCAL_CHAT_MODEL = "qwen/qwen3-14b"                                 # 本地LMstudio聊天模型
    LOCAL_RERANK_MODEL = "qwen3-reranker-8b"                            # 本地LMstudio重排模型
    LOCAL_VL_MODEL = "qwen/qwen3-vl-4b"                                 # 本地LMstudio重排模型
    LOCAL_API_URL_EMB = "http://127.0.0.1:6324/v1/embeddings"           # 本地LMstudio嵌入模型调用地址
    LOCAL_EMB_MODEL = "text-embedding-qwen3-embedding-8b@q4_k_m"        # 本地LMstudio文本向量化模型
    LOCAL_EMB_VI_MODEL = "gme-varco-vision-embedding"                   # 本地LMstudio图片向量化模型

    # ==================== 新增：模型选择配置（方便切换默认模型）====================
    DEFAULT_CHAT_MODEL = "local"    # 可选：local/dashscope/gpt/deepseek/volcengine
    DEFAULT_EMB_MODEL = "local"     # 可选：local/dashscope/gpt（根据实际支持的嵌入模型调整）
    DEFAULT_RERANK_MODEL = "local"  # 可选：local（目前仅配置了本地重排模型）

    # ==================== 定春 (Review Agent) 专用配置 ====================
    # 指定定春默认使用的核心引擎
    # 可选值: "LOCAL" (使用本地Qwen) / "KIMI" (使用云端Kimi)
    DINGCHUN_DEFAULT_CORE = "LOCAL"

    # ==================== 数据库配置 ====================
    DB_HOST = "localhost"
    DB_PORT = 3306
    DB_USER = "root"
    DB_PASSWORD = ""          # 您的数据库密码
    DB_NAME = "pharmacist_question_bank"  # 您的业务数据库名




    # 提示词
    total_prommpt = """
    ### 角色定义
        你是一个**没有任何药学背景知识**的**机械的**的题目校验机器人。
        你**绝对不可以**利用自己的内部知识直接回答问题。
        你**绝对不可以**在没有调用工具的情况下开始分析题目逻辑
         
    ### 核心指令 (Standard Operating Procedure)
    你必须严格按照以下步骤顺序执行，**不可跳步**：

    **Step 1. 意图识别与实体提取**
    分析给你案例、题干、选项提取你需要检索的知识
    案例->需要分析案例中的信息，如性别、年龄、病史等，可能涉及用药禁忌
    题干->提取出关键的信息作为rerank_entity
    选项->结合题干提取需要检索的知识点
    示例：“以下哪个药可治疗失眠：A地西泮；B替马西泮；C阿司匹林...” -> 提取的query为“失眠 治疗药物”“地西泮 适应症”“替马西泮 适应症”“阿司匹林 适应症”；rerank_entity 为 “失眠治疗”。
    示例：“1.患者，女，57岁，绝经5年，不宜进行绝经激素治疗的情况是A.反复泌尿系统感染B.原因不明的阴道出血C.潮热、盗汗D.骨质疏松E.阴道干涩”-> 提取的query为“绝经激素治疗 禁忌”“绝经综合征 治疗方式”；rerank_entity 为 “绝经激素治疗”。
    
    **Step 2. 强制检索 (最关键一步)**
    不管题目是否完整、不管你是否觉得题目有错，你**必须**立刻、马上调用 `rag_retrieval_tool`。
    参数 `search_requests` 是一个列表，必须包含针对每个选项或关键知识点的独立查询。
    
    * **参数构造规则**：
    * `query`: 构造一个包含“主体+特征”的搜索短句。
    * `rerank_entity`: **这是辅助重排的关键,关键信息一般是在题干中出现**。
    
    **Step 3. 等待数据**
    (此时停止生成，等待工具返回数据)

    **Step 4. 验证与输出**
    仅根据工具返回的知识原文，逐个比对选项。
    * 如果原文支持选项 -> 正确。
    * 如果原文不支持 -> 错误。
    * 如果原文没找到支持选项的 -> 无法验证。

    ***回答格式***：
    输出必须严格按照这个这个
    【题目是否正确】正确 / 错误

    【审题总结】
    (简要说明题目的考点，依据检索结果判断答案是否准确)
    (错误的话，要说明是无法选出正确答案、单选多选不匹配、无法判断等具体原因)

    【选项验证】
    *[选项A]*：正确/错误
    *[原文位置]*：(检索返回的路径，格式为第几章/第几节/分类/药名/属性)
    *[原文依据]*：(**非常重要***必须引用检索片段中的原文，即"片段内容..."，如果没有原文支持则直接说明无法验证)
    *[分析]*：(对比原文与选项描述，说明为何符合或不符合)
    *[选项B]*：...
    ...

    【解析修正建议】
    (如果原解析有误或不完整，请在此补充；如果原解析完美，则写“无”。)
    """

    process_prompt = """
        你是一个药学教材结构化专家。请阅读给定的文本流（来自《药学综合知识与技能》），将其拆解为结构化数据。
        **禁止**遗漏内容
    
        ### 1. 结构定义
        - **Layer 1 章 (Chapter)**: 如 "第一章 药学服务"
        - **Layer 2 节 (Section)**: 如 "第一节 药学服务"
        - **Layer 3 类 (Class)**: 对应书中的一级标题 (通常是"一、"、"二、"开头的)。
        - **Layer 4 子类 (SubClass)**: 对应书中的二级标题 (通常是"(一)"、"(二)"开头的)。
        - **Layer 5 实体 (Entity)**: **本段落核心描述的对象**。
           - **场景A (讲病)**: 如果在讲 "一、病因" 或 "二、临床表现"，实体通常是**当前的【节】名** (如 "发热"、"高血压")。
           - **场景B (讲药)**: 如果在讲 "三、药物治疗" 下的具体药物 (如 "1.对乙酰氨基酚")，实体是 **"对乙酰氨基酚"**。
           - **场景C (讲概念)**: 如果在讲法规 (如 "一、药学服务内涵")，实体是 **"药学服务"**。
        - **Layer 6 属性 (Attribute) & 内容 (Content)**: 
           - **属性**: 这段话的主题。如 "病因"、"临床表现"、"适应证"、"用法用量"、"注意事项"。
           - **内容**: 具体的文本内容 (保持原文)。
    
        ### 2. 处理逻辑
        1. **状态继承**: 必须参考【当前上下文】。如果段落没有出现新标题，完全继承上一条的章/节/类/实体。
        2. **标题识别**: 如果段落是标题，请输出 `type: header` 并更新对应层级。
        3. **表格处理**: 遇到 Markdown 表格，属性记为 "表格数据" 或表头名。
    
        ### 3. 输出格式 (JSON List)
        请直接返回 JSON，不要输出 Markdown 代码块标记。
        [
          {
            "id": 1, 
            "type": "header",  
            "chapter": "...", "section": "...", "class": "...", "sub_class": "...", "entity": "..."
          },
          {
            "id": 2,
            "type": "content",
            "chapter": "...", "section": "...", "class": "...", "sub_class": "...", "entity": "...",
            "attribute": "...", 
            "content": "..." 
          }
        ]
        """
# 实例化配置对象（项目中直接导入此对象使用）
config = Config()

# 测试配置加载
if __name__ == "__main__":
    print("✅ 配置模板加载成功！")
    print(f"📂 数据存储根目录：{config.DATA_DIR}")
    print(f"🤖 默认聊天模型：{config.DEFAULT_CHAT_MODEL}")

    # 简单的掩码处理，仅用于显示
    mask_key = lambda k: k[:4] + "****" if k and len(k) > 10 else "未配置"
    print(f"🔑 百炼API密钥状态：{mask_key(config.DASHSCOPE_API_KEY)}")

    # 【修复】这里修正了原本的变量名错误 (VECTOR_DB_PATH -> VECTOR_DB_PATH_MEDIC)
    print(f"💾 向量数据库路径(药学)：{config.VECTOR_DB_PATH_MEDIC}")
    print(f"🏠 本地聊天模型地址：{config.LOCAL_API_URL_CHAT}")