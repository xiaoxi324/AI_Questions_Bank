import chromadb
import os

# 数据库路径
DB_PATH = r"G:/KnowledgeBase/vectorizer_medic"


def inspect_db():
    if not os.path.exists(DB_PATH):
        print(f"❌ 路径不存在: {DB_PATH}")
        return

    print(f"📂 连接数据库: {DB_PATH}")
    client = chromadb.PersistentClient(path=DB_PATH)

    # 1. 获取所有集合列表
    collections = client.list_collections()
    print(f"🔍 共发现 {len(collections)} 个集合:\n")

    # 先打印所有集合名称，方便你确认哪个是“存信息的集合”
    print("📋 集合列表清单:")
    for idx, col in enumerate(collections):
        print(f"  [{idx + 1}] {col.name}")
    print("-" * 50)

    # 2. 遍历集合，查看书籍来源
    for col in collections:
        print(f"\n====== 正在分析集合: {col.name} ======")
        count = col.count()
        print(f"🔢 数据总量: {count} 条")

        # 如果是那个专门存信息的集合（通常数据量很少），我们直接打印所有内容
        if count < 100:
            print("💡 数据量较少，可能是【索引/信息集合】，直接展示内容:")
            # 获取所有数据（只看 document 或 metadata）
            data = col.get()
            # 尝试打印 documents 或 metadatas
            for i, doc in enumerate(data['documents']):
                meta = data['metadatas'][i] if data['metadatas'] else "无元数据"
                print(f"  - ID: {data['ids'][i]}")
                print(f"    内容: {doc}")
                print(f"    元数据: {meta}")

        # 如果是大数据集合，我们统计“来源文件”字段
        else:
            print("📚 正在统计由于数据量大，正在提取【来源文件】列表 (请稍候)...")

            # 为了速度，只请求 metadatas 字段
            # limit=None 可能会内存溢出，如果数据量极大建议分批，2万条通常没问题
            results = col.get(include=['metadatas'])

            distinct_books = set()
            file_key = "来源文件"  # 你指定的字段名

            for meta in results['metadatas']:
                if meta and file_key in meta:
                    distinct_books.add(meta[file_key])

            if distinct_books:
                print(f"✅ 在此集合中发现 {len(distinct_books)} 本书/文件:")
                for book in sorted(list(distinct_books)):
                    print(f"  📖 {book}")
            else:
                print("⚠️ 未在此集合的元数据中找到 '来源文件' 字段。")


if __name__ == "__main__":
    inspect_db()