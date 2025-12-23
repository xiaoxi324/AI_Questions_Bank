import os
import sys
import chromadb
from typing import List, Dict

# === 1. 环境路径修复 ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入配置和工具
from config import config
from backend.tools.tools_sql_connect import db
from backend.tools.tools_call_ai import call_ai_emb

# === 2. 配置 ===
# 数据库路径 (保持用同一个数据库文件夹)
VECTOR_DB_PATH = getattr(config, "VECTOR_DB_PATH_MEDIC", "G:/KnowledgeBase/vectorizer_medic")
# 新集合名称
COLLECTION_NAME = "Case_Question"
# 向量维度
EMBEDDING_DIM = getattr(config, "EMBEDDING_DIM", 4096)


# ==================== 3. 核心逻辑 ====================

def fetch_data_from_sql():
    """从 MySQL 获取所有案例题"""
    print("Output: 📡 正在从 MySQL 读取案例数据...")
    sql = "SELECT * FROM case_question"
    try:
        # fetch_all=True 假设你的工具支持，如果不支持请自行调整
        rows = db.execute_query(sql)
        print(f"✅ 获取到 {len(rows)} 条数据")
        return rows
    except Exception as e:
        print(f"❌ 数据库读取失败: {e}")
        return []


def init_chroma():
    """初始化 ChromaDB 客户端"""
    if not os.path.exists(VECTOR_DB_PATH):
        os.makedirs(VECTOR_DB_PATH, exist_ok=True)

    client = chromadb.PersistentClient(path=VECTOR_DB_PATH)

    # 获取或创建集合
    # metadata 用于描述这个集合是干嘛的
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "临床案例分析题库：包含案例背景与问题"}
    )
    return client, collection


def process_and_import():
    """主流程"""
    # 1. 获取数据
    rows = fetch_data_from_sql()
    if not rows:
        return

    # 2. 初始化向量库
    client, collection = init_chroma()
    print(f"📂 连接向量库: {VECTOR_DB_PATH}")
    print(f"📦 目标集合: {COLLECTION_NAME}")

    # 3. 循环处理
    total = len(rows)
    success_count = 0

    print(f"🚀 开始向量化并存入 (总计 {total} 条)...")

    for index, row in enumerate(rows):
        try:
            # === A. 构造向量文本 ===
            # 格式：[案例]... [问题]...
            # 这种结构让 AI 检索时既能匹配病情，又能匹配问题点
            case_txt = row.get('case_content', '') or ""
            stem_txt = row.get('stem', '') or ""

            # 如果没有案例内容，只存问题；如果有，则组合
            if not case_txt:
                vector_text = f"【问题】{stem_txt}"
            else:
                vector_text = f"【案例】{case_txt}\n【问题】{stem_txt}"

            # === B. 构造 Metadata ===
            # 存入一些检索后 AI 可能需要的关键信息，避免回查 SQL
            # 注意：Metadata 的值必须是 str, int, float, bool
            meta = {
                "db_id": row['question_id'],  # 数据库主键
                "source_id": row.get('source', '未知'),  # 原始文件中的 ID (78xxxx)
                "answer": row.get('answer', ''),  # 答案
                "type": "case_analysis"
            }

            # === C. 向量化 ===
            emb = call_ai_emb(vector_text)

            if emb:
                # === D. 写入 Chroma ===
                # 使用 source_id 作为向量库的主键 ID，方便去重
                # 如果 source 为空，则使用 db_id
                unique_id = str(row.get('source')) if row.get('source') else f"db_{row['question_id']}"

                collection.upsert(
                    ids=[unique_id],
                    documents=[vector_text],
                    embeddings=[emb],
                    metadatas=[meta]
                )
                success_count += 1

                # 打印进度
                if success_count % 10 == 0:
                    print(f"   ⏳ 进度: {success_count}/{total}")
            else:
                print(f"   ⚠️ 跳过: ID {row['question_id']} 向量化返回空")

        except Exception as e:
            print(f"   ❌ 处理出错 (ID: {row.get('question_id')}): {e}")

    print("=" * 50)
    print(f"🎉 入库完成！成功: {success_count} / 总数: {total}")
    print(f"📈 集合当前总数据量: {collection.count()}")


# ==================== 4. 检索测试 ====================
def test_search():
    print("\n🔍 执行检索测试...")
    client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
    col = client.get_collection(COLLECTION_NAME)

    # 模拟一个模糊的病情描述
    query = "患者高血压，出现左侧肢体无力，怀疑脑梗"
    print(f"❓ 提问: {query}")

    vec = call_ai_emb(query)
    results = col.query(query_embeddings=[vec], n_results=2)

    for i, doc in enumerate(results['documents'][0]):
        meta = results['metadatas'][0][i]
        print(f"\n--- 结果 {i + 1} (ID: {results['ids'][0][i]}) ---")
        print(f"📄 内容: {doc[:100]}...")  # 只打印前100字
        print(f"🏷️ 答案: {meta['answer']}")


if __name__ == "__main__":
    # 1. 执行导入
    process_and_import()

    # 2. 测试一下
    test_search()