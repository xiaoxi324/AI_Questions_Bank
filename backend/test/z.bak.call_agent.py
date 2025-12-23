from typing import List, Optional
from langchain.tools import tool
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
import chromadb

# 本地方法导入
from backend.tools.tools_call_ai import call_ai_emb, call_ai_rerank

# 1. 初始化配置
from config import config


# 1.1 有效内容过滤器
def _is_valid_content(full_doc_text: str) -> bool:
    """
    判断片段是否为有效内容。
    过滤掉：纯标题、空标签、字数极少的内容。
    """
    try:
        # 我们的存储格式通常是 "... | 内容：实际内容"
        # 通过分隔符提取最后一部分
        if "| 内容：" in full_doc_text:
            real_content = full_doc_text.split("| 内容：")[-1].strip()
        else:
            # 如果格式不匹配，保守起见，保留它
            real_content = full_doc_text.strip()

        # 规则 1: 过滤极短内容 (少于 10 个字通常不是考点)
        if len(real_content) < 10:
            return False

        # 规则 2: 过滤纯标签 (如 "【子类介绍】")
        if real_content.startswith("【") and real_content.endswith("】") and len(real_content) < 15:
            return False

        # 规则 3: 过滤纯层级标题 (如 "第一节 镇静催眠药")
        # 这里用启发式规则：如果包含"第一节"、"一、"且长度短
        if any(x in real_content for x in ["第一节", "一、", "二、", "三、"]) and len(real_content) < 20:
            return False

        return True

    except Exception:
        return True # 发生错误时默认保留

# 2. 定义工具
# 2. 定义工具
@tool
def rag_retrieval_tool(
        query: str,
        drugs: Optional[List[str]] = None,
        top_k: int = 3,
        offset: int = 0
) -> str:
    """
    RAG知识库检索工具（适配阶梯式检索与参阅补充逻辑）
    参数说明：
        query: 需查询的药物属性
        drugs: 目标药物列表
        top_k: 本次检索需返回的片段数量
        offset: 跳过的前置片段数量
    """
    try:
        chroma_client = chromadb.PersistentClient(path=config.VECTOR_DB_PATH)
        collection = chroma_client.get_collection(name=config.VECTOR_DB_COLLECTION)

        # 1. 向量化
        if drugs:
            full_queries = [f"{drug} {query}" for drug in drugs]
            query_embs = call_ai_emb(texts=full_queries, dimensions=config.EMBEDDING_DIM)
        else:
            emb = call_ai_emb(texts=query, dimensions=config.EMBEDDING_DIM)
            query_embs = [emb] if emb and isinstance(emb[0], float) else emb

        if not query_embs:
            return "检索失败：无法生成向量"

        formatted = ""
        target_labels = drugs or [query]

        # 2. 执行检索 (扩大召回范围，预留被过滤掉的空间)
        candidates_num = offset + top_k + 15

        # === 打印点 1: 启动检索 ===
        print(f"\n[AGENT TOOL DEBUG] 启动检索：")
        print(f"  --> 目标标签/查询：{target_labels}")
        print(f"  --> 本次从向量数据库召回 {candidates_num} 条片段（包含 offset/top_k/预留冗余）")

        results = collection.query(
            query_embeddings=query_embs,
            n_results=candidates_num,
            include=["documents", "distances"]
        )

        if not results.get("documents"):
            return "未检索到相关内容"

        for i, label in enumerate(target_labels):
            if i >= len(results["documents"]): break

            docs_group = results["documents"][i]

            # === 打印点 2: 启动 Rerank ===
            print(f"[AGENT TOOL DEBUG] 开始重排/过滤：")
            print(f"  --> 正在让 Rerank 模型对召回的 {len(docs_group)} 条片段进行重排...")

            # 3. Rerank (重排序)
            # 将所有候选片段都送去重排
            rerank_results = call_ai_rerank(
                query=f"{label} {query}",
                documents=docs_group,
                top_n=candidates_num  # 全部重排
            )

            # 4. 过滤无效片段 (Filter)
            valid_results = []
            for item in rerank_results:
                # item = {'text': ..., 'score': ..., 'index': ...}
                if _is_valid_content(item['text']):
                    # 可以在这里加分数阈值，例如 score > 1.0
                    if item['score'] > 1.0:
                        valid_results.append(item)

            # 5. 切片 (Slice)
            # 在过滤后的列表中进行 offset 和 top_k 切片
            if len(valid_results) > offset:
                final_results = valid_results[offset:offset + top_k]
            else:
                final_results = []

            # === 打印点 3: 最终片段和等待信息 ===
            print("\n[AGENT TOOL DEBUG] Rerank/过滤后的最终片段：")
            if final_results:
                for k, item in enumerate(final_results, 1):
                    # 打印最终被选中送给 LLM 的片段
                    print(f"  ✅ {k}. [Score:{item['score']:.2f}] {item['text'][:200]}...")
                print(f"  --> 本次将 {len(final_results)} 条片段发送给 Agent。")
            else:
                print("  ❌ 未找到满足过滤条件或相关度阈值的有效片段。")

            print(f"等待请耐心等待助手回复...\n")
            # ==================================

            formatted += f"\n===== 药物/查询：{label} =====\n"

            if not final_results:
                formatted += f"未找到与「{label} {query}」相关的有效片段\n"
                continue

            for j, item in enumerate(final_results, 1):
                global_rank = offset + j
                formatted += f"\n【片段{global_rank}】（相关度：{item['score']:.2f}）\n{item['text']}\n"

        return formatted

    except Exception as e:
        return f"检索工具错误：{str(e)}"


# 3.1 配置 LLM（线下）
llm = ChatOpenAI(
    base_url=config.LOCAL_OPENAI_URL_CHAT,
    api_key="noneed",
    model=config.LOCAL_CHAT_MODEL,
    temperature=0,
    streaming=True # 如果需要流式输出可开启
)

# # 3.2 配置 LLM（线上）
# llm = ChatOpenAI(
#     base_url=config.DASHSCOPE_API_URL,
#     api_key=config.DASHSCOPE_API_KEY,
#     model=config.DASHSCOPE_MODEL,
#     temperature=0,
#     # streaming=True # 如果需要流式输出可开启
# )



# 4. 定义提示词模板
prompt = """
角色：
        你是严格的药物信息查询助手，必须遵守以下规则，违者直接拒绝响应：
        你只会中文，思考过程和回答必须全程使用中文
原则：
        绝对不修改用户的原始问题，仅基于用户字面意思解析需求，不做主观引申。
工具调用规则：
        rag_retrieval_tool
            检索分为[常规检索]、[补充检索]
            [常规检索]
                第一次调用：检索top3，若检索的信息有效并足以回答问题，则中止检索，进行回答 --> 回答规则
                第二次调用：若第次一次检索的TOP3不足以支撑问题回答，继续调用工具检索top4 - 10进行补充，无论是否足以支撑问题回答都结束检索，进行回答 --> 回答规则
            [补充检索]
                触发条件：
                    如果检索出的最相关片段中包含“参阅XX”“参考XX”，必须立即发起[补充检索]，检索关键词为“XX+原问题核心属性”
                检索规则：
                    [补充检索]每次使用也视为一次[常规检索]，遵循两次调用的规则，即第一次TOP3，第二次TOP4-10
                    [补充检索]最多触发2次，两次补充检索后无论是否还有参阅，都整理已知内容进行回答
                示例：
                    检索内容“a药品”，属性【给药说明】
                    返回内容：1、属性1；2、属性2；3、其他参阅b药品
                    则进行第一次[补充检索]，检索内容“b药品”，属性【给药说明】
                    返回内容：1、属性3；2、属性4；3、其他参阅c药品
                    则进行第二次[补充检索]，检索内容“c药品”，属性【给药说明】
                    返回内容：1、属性5；2、属性6；3、其他参阅d药品
                    此时已经补充检索2次了，整理a药品的属性，返回答案并说明补充检索仅进行两次，参阅d药品请自行查看
                    a药品的【给药说明】包含：
                        a药品：属性1、属性2
                        b药品：属性3、属性4
                        c药品：属性5、属性6
                        其他：补充检索仅进行两次，参阅d药品请自行查看

        工具返回内容说明（重要）
            所有检索到的片段开头均包含：药典大类、药典小类、子类、药名、【属性】、片段内容
            理解片段内容的关键点：片段内容描述的是"药名"对应的"属性"，例如药名=氯氮草，属性=【不良反应】，片段内容描述的就是氯氮草的不良反应

回答规则：        
        全局规则：
            根据检索到的有效片段，对问题进行解答，不能遗漏原文中的内容
        补充规则：
            1.  若检索到“参阅XX”且补充检索到XX的具体内容，必须将XX的相关信息整合到回答中，明确标注来源；  
            2.  若检索到的片段不足以支撑回答，则如实回答根据检索的内容无法作答

回答格式：
        1.  选择题必须按照以下格式回答
            【正确选项】XXX
            【解析】
             1. 选项A：（此处必须放原文所处章节，例如第一章第五小节）此处必须放原文片段
             2. 选项B：（此处必须放原文所处章节，例如第一章第五小节）此处必须放原文片段
             ...（依次对比所有选项）
             结论：XXX（基于原文对比得出）

        2.  其他题目必须按照以下格式回答
            【回答】
            具体的回答内容，可以完整的回答用户的问题，（非常重要）不能遗漏任何原文中的内容
            【解析】
            回答内容的解析过程，包含用了什么工具，如何推理出回答的过程
            【原文依据】
            第几章第几小节，片段原文全部打印
"""

# 5. 创建 Agent
agent = create_agent(
    llm,
    tools=[rag_retrieval_tool],
    system_prompt=prompt,
    debug=False,
    # cache=None, # cache参数在部分新版中已移除，如报错请注释掉
)

# 6. 测试 Agent
if __name__ == "__main__":
    user_query = """
治疗三叉神经痛可选用的药物是
A.卡马西平
B.苯妥英钠
C.地西泮
D.丙戊酸钠
E.拉莫三嗪
    """

    print(f"用户提问：\n{user_query}")
    print("-" * 50)

    # 构造 LangChain 标准消息格式
    result = agent.invoke({
        "messages.js": [HumanMessage(content=user_query)]
    })

    # 打印结果逻辑优化：兼容 result 是字典或直接是对象的情况
    messages = result.get("messages.js") if isinstance(result, dict) else result

    if messages:
        for msg in messages:
            if isinstance(msg, AIMessage):
                print("【AI 消息】")
                print(msg.content.strip() + "\n")
            elif isinstance(msg, ToolMessage):
                print("【工具消息】")
                # === 修正：取消截断，打印完整内容 ===
                print(msg.content.strip() + "\n")