import os
import chromadb
from typing import Optional
from config import config
from backend.tools.tools_call_ai import call_ai_emb
import time

# ==================== 配置区 ====================
DEFAULT_DB_PATH = config.VECTOR_DB_PATH_MEDIC
DEFAULT_COLLECTION = "Pharmacopoeia"
TOP_K = 5
VECTOR_DIM = config.EMBEDDING_DIM

# ==================== 基础工具函数 ====================
def get_chroma_client(path: str) -> Optional[chromadb.PersistentClient]:
    if not os.path.exists(path):
        print(f"❌ 路径不存在：{path}")
        return None
    try:
        return chromadb.PersistentClient(path=path)
    except Exception as e:
        print(f"❌ 连接数据库失败：{str(e)}")
        return None

def get_target_collection(client: chromadb.PersistentClient, col_name: str) -> Optional[chromadb.Collection]:
    try:
        return client.get_collection(name=col_name)
    except ValueError:
        print(f"❌ 集合不存在：{col_name}")
        return None
    except Exception as e:
        print(f"❌ 获取集合失败：{str(e)}")
        return None

# ==================== 方法一：元数据模糊匹配（彻底修复） ====================
def query_by_metadata(
    query_key: str,
    query_value: str,
    db_path: str = DEFAULT_DB_PATH,
    col_name: str = DEFAULT_COLLECTION,
    limit: int = TOP_K
) -> None:
    print("\n" + "="*30 + " 🔍 元数据模糊匹配查询 " + "="*30)
    print(f"📌 匹配字段：{query_key}")
    print(f"📌 匹配值：{query_value}")
    print(f"📌 目标集合：{col_name}")
    print("-"*70)

    client = get_chroma_client(db_path)
    if not client:
        return
    collection = get_target_collection(client, col_name)
    if not collection:
        return

    # 最终修复：get 方法默认返回 ids，无需放在 include 中（与 query 方法一致）
    try:
        # include 中移除 ids，仅指定需要的字段（ids 会自动返回）
        all_results = collection.get(include=["metadatas", "documents"])
        ids = all_results.get("ids", [])  # ids 默认返回，直接获取
        docs = all_results.get("documents", [])
        metas = all_results.get("metadatas", [])

        # 内存模糊匹配（不区分大小写，兼容中文）
        matched_data = []
        for id_str, doc, meta in zip(ids, docs, metas):
            if query_key in meta and query_value.lower() in str(meta[query_key]).lower():
                matched_data.append((id_str, doc, meta))
                if len(matched_data) >= limit:
                    break

        if not matched_data:
            print(f"⚠️ 未找到匹配结果（{query_key} 包含 {query_value}）")
            return

        print(f"✅ 找到 {len(matched_data)} 条匹配结果：\n")
        for idx, (id_str, doc, meta) in enumerate(matched_data, 1):
            print(f"【结果 {idx}】ID: {id_str}")
            print("-"*50)
            print("📋 元数据：")
            for k, v in meta.items():
                if k == query_key and query_value.lower() in str(v).lower():
                    print(f"  - {k}: 🔴{v}🔴")  # 高亮匹配字段
                else:
                    print(f"  - {k}: {v}")
            print("📄 文本内容：")
            formatted_doc = doc.strip().replace('\n', '\n    ')[:200]
            print(f"  {formatted_doc}..." if len(formatted_doc) > 150 else f"  {formatted_doc}")
            print("-"*50 + "\n")

    except Exception as e:
        print(f"❌ 查询失败：{str(e)}")
        print(f"⚠️ 提示：请确认元数据字段 {query_key} 存在（可选字段：药名、属性、章名、节名、来源文件等）")

# ==================== 方法二：向量语义检索（已正常，优化显示） ====================
def query_by_vector(
    query_text: str,
    db_path: str = DEFAULT_DB_PATH,
    col_name: str = DEFAULT_COLLECTION,
    top_k: int = TOP_K
) -> None:
    print("\n" + "="*30 + " 🧠 向量语义检索 " + "="*30)
    print(f"📌 查询词：{query_text}")
    print(f"📌 目标集合：{col_name}")
    print(f"📌 返回Top{top_k}结果")
    print("-"*70)

    client = get_chroma_client(db_path)
    if not client:
        return
    collection = get_target_collection(client, col_name)
    if not collection:
        return

    # 查询词向量化
    print("⏳ 正在向量化查询词...")
    try:
        query_emb = call_ai_emb(query_text, dimensions=VECTOR_DIM)
        if not query_emb or len(query_emb) != VECTOR_DIM:
            print("❌ 查询词向量化失败（向量为空或维度错误）")
            return
    except Exception as e:
        print(f"❌ 查询词向量化失败：{str(e)}")
        return

    # 执行检索
    print("⏳ 正在检索相关结果...")
    try:
        results = collection.query(
            query_embeddings=[query_emb],
            n_results=top_k,
            include=["metadatas", "documents", "distances"]
        )
    except Exception as e:
        print(f"❌ 检索失败：{str(e)}")
        return

    # 解析结果（处理二维列表）
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not ids:
        print(f"⚠️ 未找到相关结果")
        return

    # 优化显示：相似度按百分比展示，更直观
    print(f"✅ 找到 {len(ids)} 条相关结果（相似度越高越相关）：\n")
    for idx, (id_str, doc, meta, dist) in enumerate(zip(ids, docs, metas, distances), 1):
        similarity = (1 - dist) * 100  # 转换为百分比
        print(f"【结果 {idx}】ID: {id_str} | 相似度：{similarity:.2f}%")
        print("-"*50)
        print("📋 元数据：")
        for k, v in meta.items():
            print(f"  - {k}: {v}")
        print("📄 文本内容：")
        formatted_doc = doc.strip().replace('\n', '\n    ')[:300]
        print(f"  {formatted_doc}..." if len(formatted_doc) > 200 else f"  {formatted_doc}")
        print("-"*50 + "\n")

# ==================== 测试入口（新增更多实用示例） ====================
if __name__ == "__main__":
    # 测试1：元数据模糊匹配（药名包含"苯巴比妥"）
    query_by_metadata(
        query_key="药名",
        query_value="苯巴比妥",
        limit=3
    )

    time.sleep(2)

    # 测试2：元数据模糊匹配（属性包含"不良反应"）
    query_by_metadata(
        query_key="属性",
        query_value="不良反应",
        limit=2
    )

    time.sleep(2)

    # 测试3：向量语义检索（自然语言查询）
    query_by_vector(
        query_text="氯氮草的禁忌证是什么？",
        top_k=3
    )

    time.sleep(2)

    # 测试4：向量语义检索（复杂查询）
    query_by_vector(
        query_text="癫痫持续状态可以使用哪些药物？",
        top_k=4
    )