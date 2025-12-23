import sys
import os

# === 路径修复 (新增) ===
# 目的：确保在 /backend/tools/ 目录下也能导入项目根目录的 config.py
# 获取当前文件所在目录 (backend/tools)
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录 (向上跳两级: tools -> backend -> root)
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)
# ======================

import pymysql
from pymysql.cursors import DictCursor
# === 导入配置 (增加开源容错) ===
try:
    from config import config
except ImportError:
    # 这是一个给开源用户的友好提示，不影响你原本的运行
    print("❌ 错误: 找不到 config.py 配置文件。")
    print("💡 提示: 请将 config.py (或模板) 放置在项目根目录，并配置数据库信息。")
    sys.exit(1)


class DatabaseManager:
    def __init__(self):
        self.host = config.DB_HOST
        self.port = config.DB_PORT
        self.user = config.DB_USER
        self.password = config.DB_PASSWORD
        self.db_name = config.DB_NAME

    def get_connection(self):
        """获取数据库连接"""
        try:
            conn = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.db_name,
                charset='utf8mb4',
                cursorclass=DictCursor  # 让查询结果返回字典格式 {'id': 1, 'title': '...'}
            )
            return conn
        except Exception as e:
            print(f"❌ 数据库连接失败: {e}")
            return None

    def execute_update(self, sql, params=None):
        """
        执行 增/删/改 操作
        :param sql: SQL语句，参数用 %s 占位
        :param params: 参数元组或列表
        :return: 受影响的行数 (int) 或 None
        """
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cursor:
                affected_rows = cursor.execute(sql, params)
                conn.commit()  # 提交事务
                return affected_rows
        except Exception as e:
            conn.rollback()  # 出错回滚
            print(f"❌ SQL执行错误: {e}\nSQL: {sql}\nParams: {params}")
            return None
        finally:
            conn.close()

    def execute_query(self, sql, params=None, fetch_one=False):
        """
        执行 查询 操作
        :param sql: SQL语句
        :param params: 参数
        :param fetch_one: 是否只取一条数据
        :return: 字典列表 或 单个字典
        """
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                if fetch_one:
                    result = cursor.fetchone()
                else:
                    result = cursor.fetchall()
                return result
        except Exception as e:
            print(f"❌ 查询失败: {e}\nSQL: {sql}")
            return []
        finally:
            conn.close()


# 实例化一个全局对象，供其他模块直接调用
db = DatabaseManager()

# ==================== 简单的自测代码 ====================
if __name__ == "__main__":
    print(f"🔌 正在连接数据库: {config.DB_NAME}...")

    # 1. 测试连接
    conn = db.get_connection()
    if conn:
        print("✅ 连接成功！")
        conn.close()

        # 2. 测试查询表结构
        tables = db.execute_query("SHOW TABLES;")
        print(f"\n📊 当前库中的表:")
        for idx, table in enumerate(tables, 1):
            table_name = list(table.values())[0]
            print(f"  {idx}. {table_name}")

        # 3. 结构化打印每张表的字段信息
        print("\n" + "=" * 60)
        print("📋 表字段详情（字段名 | 类型 | 允许空 | 注释）")
        print("=" * 60)

        for table in tables:
            table_name = list(table.values())[0]
            print(f"\n【{table_name}】")
            # 查询字段信息（简洁版）
            fields_sql = f"""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_COMMENT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = '{config.DB_NAME}' AND TABLE_NAME = '{table_name}'
            ORDER BY ORDINAL_POSITION
            """
            fields = db.execute_query(fields_sql)
            # 格式化输出
            for field in fields:
                print(
                    f"  {field['COLUMN_NAME']:<15} | {field['DATA_TYPE']:<10} | {field['IS_NULLABLE']:<5} | {field['COLUMN_COMMENT'] or '无'}")