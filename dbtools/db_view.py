import os
import chromadb
from config import config
import time

# ==================== 配置区 ====================
DEFAULT_DB_PATH = config.VECTOR_DB_PATH_MEDIC
PREVIEW_LIMIT = 20


def get_chroma_client(path: str):
    """获取 ChromaDB 客户端"""
    if not os.path.exists(path):
        print(f"❌ 路径不存在：{path}")
        return None
    try:
        return chromadb.PersistentClient(path=path)
    except Exception as e:
        print(f"❌ 连接数据库失败：{str(e)}")
        return None


def show_database_info(db_path: str = DEFAULT_DB_PATH):
    """
    功能一：查询数据库概览信息
    """
    print("\n" + "=" * 30 + " 📊 数据库概览信息 " + "=" * 30)
    print(f"📂 数据库路径: {db_path}")

    client = get_chroma_client(db_path)
    if not client:
        return

    collections = client.list_collections()
    if not collections:
        print("⚠️ 该数据库中没有发现任何集合。")
        return

    print(f"🔍 发现 {len(collections)} 个集合：\n")

    for idx, col_obj in enumerate(collections, 1):
        col_name = col_obj.name
        print(f"--- [集合 {idx}]名称: {col_name} ---")

        try:
            collection = client.get_collection(name=col_name)
            count = collection.count()
            print(f"  🔢 数据总量: {count} 条")

            if count > 0:
                # 获取第一条数据（包含 embeddings 用于计算维度）
                sample = collection.get(limit=1, include=["embeddings", "metadatas", "documents"])

                # --- 修复点 1：使用 is not None 进行安全判断 ---
                embeddings = sample.get("embeddings")
                dim = "未知"

                # 只要不为 None 且长度大于 0，就尝试获取维度
                if embeddings is not None and len(embeddings) > 0:
                    first_vec = embeddings[0]
                    dim = len(first_vec)

                print(f"  📏 向量维度: {dim}")

                metadatas = sample.get("metadatas")
                if metadatas is not None and len(metadatas) > 0:
                    # 获取第一条数据的 keys
                    first_meta = metadatas[0]
                    # 再次防御：metadatas[0] 可能为 None
                    if first_meta:
                        keys = list(first_meta.keys())
                        print(f"  🏷️  元数据字段: {', '.join(keys)}")
            else:
                print("  ⚠️ 集合为空")

        except Exception as e:
            print(f"  ❌ 读取集合信息失败: {str(e)}")
        print("")


def preview_collections_content(db_path: str = DEFAULT_DB_PATH, limit: int = PREVIEW_LIMIT):
    """
    功能二：预览每个集合的内容
    """
    print("\n" + "=" * 30 + f" 👁️ 集合内容预览 (Top {limit}) " + "=" * 30)

    client = get_chroma_client(db_path)
    if not client:
        return

    collections = client.list_collections()
    for col_obj in collections:
        col_name = col_obj.name
        print(f"\n📁 正在预览集合: 【 {col_name} 】")

        try:
            collection = client.get_collection(name=col_name)
            count = collection.count()

            if count == 0:
                print("  (集合为空)")
                continue

            # --- 修复点 2：从 include 中移除 "ids" ---
            # ids 是默认返回的，不能放在 include 参数里
            results = collection.get(limit=limit, include=["metadatas", "documents"])

            ids = results.get("ids", [])
            docs = results.get("documents", [])
            metas = results.get("metadatas", [])

            # 安全遍历（取三者最小长度，防止数据不一致）
            safe_len = min(len(ids), len(docs), len(metas))

            for i in range(safe_len):
                print(f"\n  📝 [记录 {i + 1}/{min(limit, count)}] ID: {ids[i]}")
                print("  " + "-" * 50)

                # 打印元数据
                meta = metas[i]
                if meta:
                    print("  【元数据】:")
                    for k, v in meta.items():
                        print(f"    - {k}: {v}")

                # 打印文本
                doc = docs[i]
                print("  【文本内容】:")
                if doc:
                    formatted_doc = doc.strip().replace('\n', '\n    ')
                    print(f"    {formatted_doc}")
                else:
                    print("    (无内容)")
                print("  " + "-" * 50)

        except Exception as e:
            print(f"❌ 读取集合内容失败: {str(e)}")


if __name__ == "__main__":
    show_database_info()

    print("\n即将开始内容预览...")
    time.sleep(1)

    preview_collections_content()

