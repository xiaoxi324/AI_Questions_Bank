import os
import json
import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from config import config
from backend.tools.tools_call_ai import call_ai_emb

# ==============================================================================
# 🛠️ 【配置区域】请在这里修改参数
# ==============================================================================

# 1. 指定要入库的 JSON 文件绝对路径 (精确到 .json 文件)
TARGET_JSON_PATH = r"G:\KnowledgeBase\分词后数据\药典临床用药须知.json"

# 2. 目标集合名称 (想存到哪个集合就填哪个)
TARGET_COLLECTION_NAME = "Pharmacopoeia_Official"
# Hospital_Pharmac/Pharmacopoeia_Official/Pharmacopoeia_Proficiency

# 3. 向量数据库存储路径
VECTOR_DB_PATH = getattr(config, "VECTOR_DB_PATH_MEDIC", "G:/KnowledgeBase/vectorizer_medic")

# 4. 是否先清空该集合？ (True=删除旧集合重新导, False=追加数据)
RESET_COLLECTION = True

# 5. 嵌入维度 (跟模型保持一致)
EMBEDDING_DIM = getattr(config, "EMBEDDING_DIM", 4096)

# 6. 写入批次大小 (每处理多少条写一次库，防止内存溢出)
BATCH_SIZE = 30

# ==============================================================================


# === 1. 适配器定义 ===
class LocalEmbeddingAdapter(EmbeddingFunction):
    def __call__(self, input: Documents) -> Embeddings:
        return call_ai_emb(input, dimensions=EMBEDDING_DIM)


# === 2. 初始化数据库 ===
def init_vector_db():
    print(f"🔌 连接向量数据库: {VECTOR_DB_PATH}")
    if not os.path.exists(VECTOR_DB_PATH):
        os.makedirs(VECTOR_DB_PATH)

    client = chromadb.PersistentClient(path=VECTOR_DB_PATH)

    # 如果需要重置，先删除
    if RESET_COLLECTION:
        try:
            print(f"🗑️ 正在清空集合 [{TARGET_COLLECTION_NAME}] ...")
            client.delete_collection(TARGET_COLLECTION_NAME)
            print("✅ 旧集合已删除")
        except ValueError:
            print(f"ℹ️ 集合不存在，跳过删除")
        except Exception as e:
            print(f"⚠️ 删除集合时报错 (可忽略): {e}")

    # 创建/获取集合
    collection = client.get_or_create_collection(
        name=TARGET_COLLECTION_NAME,
        embedding_function=LocalEmbeddingAdapter(),
        metadata={"description": "单文件导入"}
    )
    return client, collection


# === 3. 核心入库逻辑 ===
def import_specific_json():
    # 0. 检查文件
    if not os.path.exists(TARGET_JSON_PATH):
        print(f"❌ 错误：找不到文件 {TARGET_JSON_PATH}")
        return

    # 1. 初始化 DB
    client, collection = init_vector_db()

    # 2. 读取 JSON
    print(f"📖 正在读取文件: {os.path.basename(TARGET_JSON_PATH)}")
    try:
        with open(TARGET_JSON_PATH, "r", encoding="utf-8") as f:
            fragments = json.load(f)
    except Exception as e:
        print(f"❌ JSON 格式错误或无法读取: {e}")
        return

    # 3. 过滤有效数据
    valid_frags = [f for f in fragments if f.get("片段内容") and len(f.get("片段内容").strip()) > 1]
    total_count = len(valid_frags)
    print(f"📊 有效片段数: {total_count}")

    if total_count == 0:
        print("⚠️ 数据为空，无需导入")
        return

    # 4. 遍历并批量写入
    batch_data = {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
    imported_count = 0
    file_prefix = os.path.splitext(os.path.basename(TARGET_JSON_PATH))[0]

    for idx, frag in enumerate(valid_frags):
        # A. 确定向量文本 (优先用预处理好的，没有则手动拼接)
        vec_text = frag.get("向量文本")
        if not vec_text:
            vec_text = f"{frag.get('组合标题', '')}：\n{frag.get('片段内容', '')}"

        # B. 向量化
        emb = call_ai_emb(vec_text, dimensions=EMBEDDING_DIM)
        if not emb:
            print(f"⚠️ 第 {idx} 条向量化失败，跳过")
            continue

        # C. 构建 Metadata (转为字符串以防报错)
        meta = {
            "来源文件": str(frag.get("来源文件", file_prefix)),
            "完整路径": str(frag.get("完整路径", "")),
            "组合标题": str(frag.get("组合标题", "")),
            "字数": int(frag.get("字数", len(vec_text))),
            "片段内容": str(frag.get("片段内容", ""))[:3000] # 防止超长
        }
        for i in range(1, 9):
            meta[f"L{i}"] = str(frag.get(f"L{i}", ""))

        # D. 放入批次
        unique_id = f"{file_prefix}_{idx}"
        batch_data["ids"].append(unique_id)
        batch_data["documents"].append(vec_text)
        batch_data["metadatas"].append(meta)
        batch_data["embeddings"].append(emb)

        # E. 批次写入
        if len(batch_data["ids"]) >= BATCH_SIZE:
            collection.add(
                ids=batch_data["ids"],
                documents=batch_data["documents"],
                metadatas=batch_data["metadatas"],
                embeddings=batch_data["embeddings"]
            )
            imported_count += len(batch_data["ids"])
            print(f"   ⏳ 已导入 {imported_count}/{total_count} ...")
            for k in batch_data: batch_data[k] = [] # 清空

    # 5. 处理剩余数据
    if batch_data["ids"]:
        collection.add(
            ids=batch_data["ids"],
            documents=batch_data["documents"],
            metadatas=batch_data["metadatas"],
            embeddings=batch_data["embeddings"]
        )
        imported_count += len(batch_data["ids"])

    print("\n" + "="*50)
    print(f"🎉 入库完成！")
    print(f"📂 文件: {os.path.basename(TARGET_JSON_PATH)}")
    print(f"🗄️ 集合: {TARGET_COLLECTION_NAME}")
    print(f"📈 成功导入: {imported_count} 条")
    print("="*50)

if __name__ == "__main__":
    import_specific_json()