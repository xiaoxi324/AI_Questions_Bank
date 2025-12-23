import os
import sys

# 将项目根目录加入路径，防止报错
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
sys.path.append(root_dir)

from backend.knowledge.knowledge_tool import list_collections, query_documents, QueryRequest
from config import config


def test_knowledge_backend():
    print("-" * 50)
    print("🚀 开始测试知识库管理模块...")
    print(f"📂 数据库路径 (config): {config.VECTOR_DB_PATH_MEDIC}")

    # 1. 测试列出集合
    print("\n1️⃣ 正在获取集合列表...")
    cols = list_collections()
    print(f"   -> 结果: {cols}")

    if not cols:
        print("❌ 错误：未找到任何集合，请检查路径是否正确！")
        return

    target_col = "Pharmacopoeia"
    if target_col not in cols:
        print(f"⚠️ 警告：默认集合 '{target_col}' 不在列表中，将使用第一个集合 '{cols[0]}' 进行测试")
        target_col = cols[0]

    # 2. 测试查询数据
    print(f"\n2️⃣ 正在查询集合 '{target_col}' 的前 5 条数据...")
    req = QueryRequest(
        collection_name=target_col,
        page=1,
        page_size=5
    )

    try:
        res = query_documents(req)
        data = res.get("data", [])
        total = res.get("total", 0)

        print(f"   -> 查询成功！总数: {total}")
        print(f"   -> 本页数据量: {len(data)}")

        if len(data) > 0:
            first_item = data[0]
            print("\n📄 [第一条数据预览]:")
            print(f"   ID: {first_item['id']}")
            print(f"   元数据: {first_item['metadata']}")
            print(f"   内容(前50字): {first_item['content'][:50]}...")
        else:
            print("   ⚠️ 集合为空，没有数据。")

    except Exception as e:
        print(f"❌ 查询出错: {e}")


if __name__ == "__main__":
    test_knowledge_backend()