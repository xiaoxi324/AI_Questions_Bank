import chromadb
import uuid
from backend.tools.tools_sql_connect import db
from backend.tools.tools_call_ai import call_ai_emb
from backend.tools.global_context import log_queue_ctx
from config import config


def emit(msg):
    print(msg)
    q = log_queue_ctx.get()
    if q: q.put(f"LOG: {msg}")


DB_PATH = getattr(config, "VECTOR_DB_PATH_MEDIC", "G:/KnowledgeBase/vectorizer_medic")
EMBEDDING_DIM = 4096


def execute_embed_task(book_id: int):
    emit(f"💉 [入库] 开始向量化 BookID={book_id}...")

    book = db.execute_query("SELECT * FROM import_books WHERE book_id=%s", (book_id,), fetch_one=True)
    # 确保使用新的集合名
    col_name = book.get("target_collection", "Pharmacopoeia_Official")

    try:
        client = chromadb.PersistentClient(path=DB_PATH)
        collection = client.get_or_create_collection(name=col_name)
    except Exception as e:
        return {"status": "error", "msg": f"向量库连接失败: {e}"}

    while True:
        # 批量获取未入库片段
        fragments = db.execute_query(
            "SELECT * FROM knowledge_fragments WHERE book_id=%s AND is_embedded=0 LIMIT 10",
            (book_id,)
        )
        if not fragments:
            emit("✅ 所有片段已入库")
            break

        ids = []
        docs = []
        metadatas = []
        frag_db_ids = []

        for frag in fragments:
            # 1. 构造向量文本
            combo_title = frag.get('combo_title', '').strip()

            # 兜底逻辑：如果 combo_title 为空，尝试从 L 层级拼凑
            if not combo_title:
                parts = []
                for i in range(1, 9):
                    val = frag.get(f'L{i}')
                    if val: parts.append(val)
                combo_title = parts[-1] if parts else "无标题"

            vector_text = f"{combo_title}：\n{frag['content']}"

            # 2. 构造完整路径 (用于展示)
            path_parts = []
            l_levels = {}
            for i in range(1, 9):
                key = f"L{i}"
                val = frag.get(key, "")
                l_levels[key] = val  # 存入 metadata，即使为空
                if val:
                    path_parts.append(val)

            full_path = " / ".join(path_parts)

            # 3. 生成固定 UUID (便于去重)
            stable_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"fragment_{frag['fragment_id']}"))
            ids.append(stable_uuid)

            docs.append(vector_text)

            # 4. 构造元数据 (适配 L1-L8)
            meta = {
                "来源文件": book['book_name'],
                "组合标题": combo_title,
                "完整路径": full_path,
                "片段内容": frag['content'],
                "字数": len(frag['content']),
                "db_fragment_id": frag['fragment_id'],
                **l_levels  # 动态解包 L1-L8
            }
            metadatas.append(meta)
            frag_db_ids.append(frag['fragment_id'])

        try:
            emit(f"   -> 正在向量化 {len(docs)} 条片段...")
            embeddings = call_ai_emb(docs, dimensions=EMBEDDING_DIM)
            if not embeddings:
                emit("   ❌ 向量化返回空，跳过本批次")
                # 避免死循环，标记为错误或跳过 (这里简单处理为继续循环，实际可加错误计数)
                continue

            # 存入 Chroma
            collection.upsert(ids=ids, documents=docs, embeddings=embeddings, metadatas=metadatas)

            # 更新数据库状态
            fmt = ','.join(['%s'] * len(frag_db_ids))
            db.execute_update(f"UPDATE knowledge_fragments SET is_embedded=1 WHERE fragment_id IN ({fmt})",
                              tuple(frag_db_ids))

            # 更新书本进度统计
            db.execute_update(
                """
                UPDATE import_books SET 
                imported_fragments = (SELECT COUNT(*) FROM knowledge_fragments WHERE book_id=%s AND is_embedded=1),
                total_fragments = (SELECT COUNT(*) FROM knowledge_fragments WHERE book_id=%s)
                WHERE book_id=%s
                """,
                (book_id, book_id, book_id))

        except Exception as e:
            emit(f"   ❌ 入库异常: {e}")
            # 遇到严重错误退出循环，防止刷屏日志
            break

    # 任务结束更新状态
    db.execute_update("UPDATE import_books SET status='embedded' WHERE book_id=%s", (book_id,))
    return {"status": "success", "msg": "入库完成"}