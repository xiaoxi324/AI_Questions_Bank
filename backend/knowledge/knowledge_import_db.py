import os
import sys
from typing import List, Dict

# 路径修复
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from backend.tools.tools_sql_connect import db


# ==================== 1. 书本管理 (import_books) ====================

def create_book_task(name: str, path: str, collection: str, batch_size: int = 15):
    """创建书本任务"""
    sql = """
    INSERT INTO import_books 
    (book_name, file_path, target_collection, batch_size, status)
    VALUES (%s, %s, %s, %s, 'ready')
    """
    try:
        conn = db.get_connection()
        with conn.cursor() as cursor:
            cursor.execute(sql, (name, path, collection, batch_size))
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        print(f"❌ [DB] 创建书本失败: {e}")
        return None


def update_book_stats(book_id: int):
    """
    自动统计并更新书本的进度字段
    (total_segments, processed_segments, total_fragments, imported_fragments)
    """
    sql_update = """
    UPDATE import_books b
    SET 
        total_segments = (SELECT COUNT(*) FROM book_segments WHERE book_id = b.book_id),
        processed_segments = (SELECT COUNT(*) FROM book_segments WHERE book_id = b.book_id AND is_processed = 1),
        total_fragments = (SELECT COUNT(*) FROM knowledge_fragments WHERE book_id = b.book_id),
        imported_fragments = (SELECT COUNT(*) FROM knowledge_fragments WHERE book_id = b.book_id AND is_embedded = 1)
    WHERE book_id = %s
    """
    db.execute_update(sql_update, (book_id,))


def update_book_status_text(book_id: int, status: str):
    sql = "UPDATE import_books SET status=%s WHERE book_id=%s"
    db.execute_update(sql, (status, book_id))


# ==================== 2. 分段管理 (book_segments) ====================

def add_segments_batch(book_id: int, book_name: str, segments: List[str]):
    """
    批量插入原始分段
    :param segments: 文本列表
    """
    if not segments: return

    sql = """
    INSERT INTO book_segments (book_id, book_name, content, segment_order, is_processed)
    VALUES (%s, %s, %s, %s, 0)
    """
    params = []
    for idx, content in enumerate(segments):
        # segment_order 从 1 开始
        params.append((book_id, book_name, content, idx + 1))

    try:
        conn = db.get_connection()
        with conn.cursor() as cursor:
            cursor.executemany(sql, params)
            conn.commit()
        # 插入后立即更新统计
        update_book_stats(book_id)
    except Exception as e:
        print(f"❌ [DB] 插入分段失败: {e}")


def get_unprocessed_segments(book_id: int, limit: int):
    """获取未处理的分段（按顺序）"""
    sql = """
    SELECT segment_id, content, segment_order 
    FROM book_segments 
    WHERE book_id = %s AND is_processed = 0 
    ORDER BY segment_order ASC 
    LIMIT %s
    """
    return db.execute_query(sql, (book_id, limit))


def mark_segments_as_processed(segment_ids: List[int]):
    """标记分段为已处理"""
    if not segment_ids: return
    format_strings = ','.join(['%s'] * len(segment_ids))
    sql = f"UPDATE book_segments SET is_processed = 1 WHERE segment_id IN ({format_strings})"
    db.execute_update(sql, tuple(segment_ids))


# ==================== 3. 片段管理 (knowledge_fragments) - 核心修改区 ====================

def add_fragments_batch(book_id: int, book_name: str, items: List[Dict]):
    """
    批量插入AI生成的结构化片段 (适配 L1-L8 结构)
    """
    if not items: return

    # 构造 SQL：包含 L1 到 L8 和 组合标题
    sql = """
    INSERT INTO knowledge_fragments 
    (book_id, book_name, 
     L1, L2, L3, L4, L5, L6, L7, L8, 
     combo_title, content, is_embedded)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
    """

    params = []
    for item in items:
        # 优先获取 combo_title，如果没有则尝试拼接
        combo = item.get('combo_title')
        if not combo:
            # 简单的兜底逻辑：取最后一个非空的L层级作为标题
            # 但通常 AI 处理模块应该已经生成好 combo_title 了
            parts = []
            for i in range(1, 9):
                val = item.get(f'L{i}')
                if val: parts.append(val)
            combo = parts[-1] if parts else "无标题"

        params.append((
            book_id,
            book_name,
            item.get('L1', ''),
            item.get('L2', ''),
            item.get('L3', ''),
            item.get('L4', ''),
            item.get('L5', ''),
            item.get('L6', ''),
            item.get('L7', ''),
            item.get('L8', ''),
            combo,  # 对应 combo_title
            item.get('content', '')
        ))

    try:
        conn = db.get_connection()
        with conn.cursor() as cursor:
            cursor.executemany(sql, params)
            conn.commit()
        # 更新统计
        update_book_stats(book_id)
    except Exception as e:
        print(f"❌ [DB] 插入片段失败: {e}")


def get_unembedded_fragments(book_id: int):
    """获取未入向量库的片段"""
    sql = "SELECT * FROM knowledge_fragments WHERE book_id = %s AND is_embedded = 0"
    return db.execute_query(sql, (book_id,))


def mark_fragment_as_embedded(fragment_id: int):
    """标记片段已入向量库"""
    sql = "UPDATE knowledge_fragments SET is_embedded = 1 WHERE fragment_id = %s"
    db.execute_update(sql, (fragment_id,))


# ==================== 系统日志 (System Logs) ====================

def add_system_log(log_type: str, source: str, message: str):
    """写入系统日志"""
    sql = "INSERT INTO system_logs (log_type, source, message) VALUES (%s, %s, %s)"
    try:
        db.execute_update(sql, (log_type, source, message))
    except Exception as e:
        print(f"❌ 日志写入失败: {e}")


def get_system_logs(limit=50):
    """获取最新日志"""
    sql = "SELECT * FROM system_logs ORDER BY create_time DESC LIMIT %s"
    return db.execute_query(sql, (limit,))


def clear_system_logs():
    """清空日志"""
    return db.execute_update("TRUNCATE TABLE system_logs")