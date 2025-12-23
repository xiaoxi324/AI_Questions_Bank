import os
import sys
import chromadb
import time
from collections import defaultdict

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
VECTOR_DB_PATH = getattr(config, "VECTOR_DB_PATH_MEDIC", "G:/KnowledgeBase/vectorizer_medic")
COLLECTION_NAME = "Case_Question"
EMBEDDING_DIM = getattr(config, "EMBEDDING_DIM", 4096)


# ==================== 核心逻辑 ====================

def reset_collection():
    """强制删除并重新创建集合"""
    print(f"🧹 正在清理向量库集合: {COLLECTION_NAME} ...")
    if not os.path.exists(VECTOR_DB_PATH):
        os.makedirs(VECTOR_DB_PATH, exist_ok=True)

    client = chromadb.PersistentClient(path=VECTOR_DB_PATH)

    try:
        client.delete_collection(COLLECTION_NAME)
        print("   - 旧集合已删除")
    except:
        pass  # 集合不存在则忽略

    # 重建
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "案例分析题库（聚合版）：一个Vector对应一个案例+多个问题"}
    )
    print("   - 新集合创建成功")
    return client, collection


def fetch_and_group_data():
    """从 MySQL 获取并按案例分组"""
    print("📡 正在从 MySQL 读取数据...")
    sql = "SELECT * FROM case_question ORDER BY question_id ASC"  # 排序保证顺序
    rows = db.execute_query(sql)
    print(f"   - 原始题目数量: {len(rows)}")

    grouped_data = []

    # 临时字典用于分组： key=case_content_hash, value=group_obj
    # 注意：这里假设 case_content 相同的即为同一组
    groups_map = defaultdict(lambda: {
        "case_content": "",
        "questions": [],
        "ids": [],
        "sources": [],
        "answers": []
    })

    # 独立题目列表（没有共用题干的）
    standalone_items = []

    for row in rows:
        case_txt = row.get('case_content', '')

        if case_txt and len(case_txt.strip()) > 5:
            # 有案例背景，归入组
            # 使用内容作为 Key (去除首尾空格)
            key = case_txt.strip()
            groups_map[key]["case_content"] = key
            groups_map[key]["questions"].append(row['stem'])
            groups_map[key]["ids"].append(str(row['question_id']))
            groups_map[key]["sources"].append(str(row.get('source', '')))
            groups_map[key]["answers"].append(row['answer'])
        else:
            # 无案例背景，作为单题处理
            standalone_items.append(row)

    # 将 Map 转为 List
    grouped_data = list(groups_map.values())

    print(f"✅ 分组完成：")
    print(f"   - 共用案例组: {len(grouped_data)} 组 (包含多个小题)")
    print(f"   - 独立小题: {len(standalone_items)} 条")

    return grouped_data, standalone_items


def process_import():
    client, collection = reset_collection()
    grouped_data, standalone_items = fetch_and_group_data()

    total_tasks = len(grouped_data) + len(standalone_items)
    print(f"🚀 开始向量化并入库，共 {total_tasks} 个向量条目...")

    count = 0

    # --- 1. 处理共用案例组 ---
    for group in grouped_data:
        try:
            # 构造聚合文本
            # 格式：
            # 【共用案例】...
            # 【问题1】... (答案: A)
            # 【问题2】... (答案: B)

            combined_text = f"【共用案例】\n{group['case_content']}\n"
            for i, stem in enumerate(group['questions']):
                ans = group['answers'][i]
                combined_text += f"\n【问题{i + 1}】{stem}\n(答案: {ans})"

            # 构造 Metadata
            # db_ids 存为 "101,102,103"
            meta = {
                "db_ids": ",".join(group['ids']),
                "source_ids": ",".join(group['sources']),
                "type": "grouped_case",
                "question_count": len(group['ids']),
                "preview": group['case_content'][:50]  # 预览用
            }

            # ID 使用第一个题目的 source_id 加后缀
            unique_id = f"group_{group['sources'][0]}"

            # 向量化
            emb = call_ai_emb(combined_text)
            if emb:
                collection.add(
                    ids=[unique_id],
                    documents=[combined_text],
                    embeddings=[emb],
                    metadatas=[meta]
                )
                count += 1
                print(f"   [Group] 存入组 ID: {unique_id} (含 {len(group['ids'])} 题)")

        except Exception as e:
            print(f"   ❌ 处理组失败: {e}")

    # --- 2. 处理独立题目 ---
    for row in standalone_items:
        try:
            vector_text = f"【问题】{row['stem']}\n(答案: {row['answer']})"

            meta = {
                "db_ids": str(row['question_id']),
                "source_ids": str(row.get('source', '')),
                "type": "single_question",
                "question_count": 1,
                "preview": row['stem'][:50]
            }

            unique_id = f"single_{row.get('source', row['question_id'])}"

            emb = call_ai_emb(vector_text)
            if emb:
                collection.add(
                    ids=[unique_id],
                    documents=[vector_text],
                    embeddings=[emb],
                    metadatas=[meta]
                )
                count += 1
        except Exception as e:
            print(f"   ❌ 处理单题失败: {e}")

    print("=" * 50)
    print(f"🎉 全部完成！")
    print(f"   - 实际存入向量库条目: {count}")
    print(f"   - 向量库当前总数: {collection.count()}")


if __name__ == "__main__":
    process_import()