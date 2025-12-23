import sys
import os
from typing import Dict, Optional

# === 路径修复 ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)
# ======================

from backend.tools.tools_sql_connect import db

# 尝试导入 config，如果失败也不要崩，保持最基本的运行能力
try:
    from config import config
except ImportError:
    config = None

from backend.dingchun.dingchun_core_local import ReviewAgentLocal
from backend.dingchun.dingchun_core_kimi import ReviewAgentKimi


class ReviewAgentDispatcher:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ReviewAgentDispatcher, cls).__new__(cls)
            cls._instance.local_agent = None
            cls._instance.kimi_agent = None
        return cls._instance

    def review_and_save(self, question_id: int, model_type: Optional[str] = None) -> Dict:
        """
        核心入口
        :param question_id: 题目ID
        :param model_type: 可选。如果指定 "KIMI" 或 "LOCAL" 则强制使用。如果不传，则走配置。
        """

        # === 核心逻辑修改：双重保险 ===
        # 优先级 1: 函数传参 (e.g. review_and_save(1, "KIMI")) -> 强制覆盖
        # 优先级 2: Config 配置 (e.g. config.DINGCHUN_DEFAULT_CORE)
        # 优先级 3: 默认兜底 -> "LOCAL" (防止 config 没配或 config 文件缺失)

        if model_type:
            target_core = model_type
        else:
            # getattr(对象, 属性名, 默认值) -> 即使 config 里没有这个变量，也会返回 "LOCAL"
            if config:
                target_core = getattr(config, "DINGCHUN_DEFAULT_CORE", "LOCAL")
            else:
                target_core = "LOCAL"

        target_core = target_core.upper()  # 转大写，容错

        print(f"🕹️ [定春调度器] 收到任务: ID={question_id}, 核心策略={target_core}")

        try:
            # 1. 查库
            sql = "SELECT * FROM pharmacist_questions WHERE question_id = %s"
            question_data = db.execute_query(sql, (question_id,), fetch_one=True)

            if not question_data:
                return {"status": "error", "msg": f"题目 ID {question_id} 不存在"}

            # 2. 调度逻辑 (保持不变)
            if target_core == "KIMI":
                if not self.kimi_agent:
                    print("🔌 [懒加载] 初始化 KIMI 核心...")
                    self.kimi_agent = ReviewAgentKimi()

                # 兼容不同方法名的调用
                if hasattr(self.kimi_agent, 'review_question'):
                    return self.kimi_agent.review_question(question_data)
                return self.kimi_agent.review_and_save(question_id)

            else:  # 默认为 LOCAL
                if not self.local_agent:
                    print("🔌 [懒加载] 初始化 LOCAL 核心...")
                    self.local_agent = ReviewAgentLocal()

                if hasattr(self.local_agent, 'review_question'):
                    return self.local_agent.review_question(question_data)
                return self.local_agent.review_and_save(question_id)

        except Exception as e:
            print(f"❌ [定春调度器] 异常: {str(e)}")
            return {"status": "error", "msg": str(e)}


dingchun = ReviewAgentDispatcher()