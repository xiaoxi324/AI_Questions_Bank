import threading
import time
from typing import List, Dict
from backend.tools.tools_sql_connect import db
# 引入具体的AI执行模块
from backend.dingchun.dingchun import dingchun
from backend.dingchun.call_other_ai import other_ai

# ==================== 配置区 ====================

# 【修正点】: 在 SQL 字符串中，% 必须转义为 %%，否则会被当做参数占位符报错
AI_CONFIG = {
    'dingchun': {
        'db_pattern': '定春%%',  # 修正：定春% -> 定春%%
        'func': lambda qid: dingchun.review_and_save(qid, "LOCAL"),
        'col': 'dingchun_status'
    },
    'qwen': {
        'db_pattern': 'Qwen%%',  # 修正
        'func': other_ai.review_by_qwen,
        'col': 'qwen_status'
    },
    'kimi': {
        'db_pattern': 'Kimi%%',  # 修正
        'func': other_ai.review_by_kimi,
        'col': 'kimi_status'
    },
    'doubao': {
        'db_pattern': 'Doubao%%',  # 修正
        'func': other_ai.review_by_doubao,
        'col': 'doubao_status'
    }
}

STOP_FLAG = False
WORKER_THREADS = []


def init_database():
    """确保进度表存在"""
    sql = """
    CREATE TABLE IF NOT EXISTS batch_task_progress (
        question_id INT PRIMARY KEY,
        dingchun_status VARCHAR(20) DEFAULT 'WAIT',
        qwen_status VARCHAR(20) DEFAULT 'WAIT',
        kimi_status VARCHAR(20) DEFAULT 'WAIT',
        doubao_status VARCHAR(20) DEFAULT 'WAIT',
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    db.execute_update(sql)


# ==================== 1. 任务初始化 (SQL 魔法) ====================

def start_new_batch(start_id: int, end_id: int, selected_ais: List[str]):
    """
    基于数据库子查询直接初始化任务表，自动识别 'DONE' 和 'SKIP'
    """
    global STOP_FLAG, WORKER_THREADS

    # 1. 停止旧线程
    STOP_FLAG = True
    for t in WORKER_THREADS:
        if t.is_alive():
            t.join(timeout=1)
    WORKER_THREADS = []
    STOP_FLAG = False

    # 2. 初始化环境
    init_database()
    db.execute_update("TRUNCATE TABLE batch_task_progress")

    # 3. 检查题目是否存在
    check_sql = "SELECT COUNT(*) as cnt FROM pharmacist_questions WHERE question_id BETWEEN %s AND %s"
    res = db.execute_query(check_sql, (start_id, end_id), fetch_one=True)
    if not res or res['cnt'] == 0:
        return {"status": "error", "msg": "该范围内没有题目"}

    # 4. 【核心逻辑】构造 INSERT INTO ... SELECT 语句

    select_parts = ["q.question_id"]

    for ai_key in ['dingchun', 'qwen', 'kimi', 'doubao']:
        config = AI_CONFIG[ai_key]
        pattern = config['db_pattern']

        if ai_key not in selected_ais:
            status_logic = "'SKIP'"
        else:
            # 这里 pattern 已经是 '定春%%'，Python 会将其转义为 SQL 中的 '定春%'
            status_logic = f"""
            CASE 
                WHEN EXISTS (
                    SELECT 1 FROM question_review_details 
                    WHERE question_id = q.question_id 
                    AND ai_name LIKE '{pattern}'
                ) THEN 'DONE'
                ELSE 'WAIT'
            END
            """
        select_parts.append(status_logic)

    insert_sql = f"""
    INSERT INTO batch_task_progress (question_id, dingchun_status, qwen_status, kimi_status, doubao_status)
    SELECT 
        {", ".join(select_parts)}
    FROM pharmacist_questions q
    WHERE q.question_id BETWEEN %s AND %s
    """

    print(f"🚀 [Batch] 执行初始化 SQL... params=({start_id}, {end_id})")

    try:
        # 执行初始化 SQL
        db.execute_update(insert_sql, (start_id, end_id))
    except Exception as e:
        print(f"❌ SQL执行错误: {e}")
        return {"status": "error", "msg": f"数据库初始化失败: {str(e)}"}

    # 5. 启动 Worker 线程
    for ai_name in selected_ais:
        t = threading.Thread(target=_worker_loop, args=(ai_name,))
        t.daemon = True
        t.start()
        WORKER_THREADS.append(t)

    return {
        "status": "success",
        "msg": "任务已初始化",
        "total_questions": res['cnt'],
        "active_ais": selected_ais
    }


def stop_batch():
    global STOP_FLAG
    STOP_FLAG = True
    return {"status": "success", "msg": "停止信号已发送"}


def get_current_progress(page=1, page_size=20):
    # 1. 统计各AI完成数
    stats = {}
    for ai in ['dingchun', 'qwen', 'kimi', 'doubao']:
        col = AI_CONFIG[ai]['col']
        sql = f"SELECT COUNT(*) as cnt FROM batch_task_progress WHERE {col} = 'DONE'"
        res = db.execute_query(sql, fetch_one=True)
        stats[ai] = res['cnt'] if res else 0

    # 2. 总条数
    total_res = db.execute_query("SELECT COUNT(*) as total FROM batch_task_progress", fetch_one=True)
    total = total_res['total'] if total_res else 0

    # 3. 列表数据 (关联查询题干)
    offset = (page - 1) * page_size
    sql_list = f"""
        SELECT p.*, left(q.stem, 20) as stem_preview 
        FROM batch_task_progress p
        LEFT JOIN pharmacist_questions q ON p.question_id = q.question_id
        ORDER BY p.question_id ASC 
        LIMIT %s OFFSET %s
    """
    rows = db.execute_query(sql_list, (page_size, offset))

    return {
        "status": "success",
        "total": total,
        "stats": stats,
        "rows": rows
    }


# ==================== 2. Worker 线程 ====================

def _worker_loop(ai_name: str):
    config = AI_CONFIG[ai_name]
    col_name = config['col']
    ai_func = config['func']

    print(f"🤖 [{ai_name}] Worker 启动...")

    while not STOP_FLAG:
        # 1. 抢任务: 只找 WAIT
        sql_find = f"SELECT question_id FROM batch_task_progress WHERE {col_name} = 'WAIT' ORDER BY question_id ASC LIMIT 1"
        task = db.execute_query(sql_find, fetch_one=True)

        if not task:
            time.sleep(2)
            check = db.execute_query(sql_find, fetch_one=True)
            if not check:
                print(f"🤖 [{ai_name}] 任务完成，线程待机。")
                break
            continue

        qid = task['question_id']

        # 2. 标记 DOING
        db.execute_update(f"UPDATE batch_task_progress SET {col_name} = 'DOING' WHERE question_id = %s", (qid,))

        try:
            # 3. 执行
            ai_func(qid)  # 写入 question_review_details

            # 4. 标记 DONE
            db.execute_update(f"UPDATE batch_task_progress SET {col_name} = 'DONE' WHERE question_id = %s", (qid,))
        except Exception as e:
            print(f"❌ [{ai_name}] ID {qid} 失败: {e}")
            db.execute_update(f"UPDATE batch_task_progress SET {col_name} = 'ERROR' WHERE question_id = %s", (qid,))

        time.sleep(0.5)