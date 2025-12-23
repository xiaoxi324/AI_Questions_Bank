# === 路径修复 (新增) ===
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
# 向上跳两级: dingchun -> backend -> root
root_dir = os.path.dirname(os.path.dirname(current_dir))
if root_dir not in sys.path:
    sys.path.append(root_dir)
# ======================

import re
from openai import OpenAI
from config import config
from backend.tools.tools_sql_connect import db


class OtherAIReviewer:
    def __init__(self):
        print("🔌 初始化辅助审题 AI (Qwen, Kimi, Doubao)...")

        # 1. Qwen
        self.client_qwen = OpenAI(
            api_key=config.DASHSCOPE_API_KEY,
            base_url=config.DASHSCOPE_API_URL
        )

        # 2. Kimi
        self.client_kimi = OpenAI(
            api_key=config.KIMI_API_KEY,
            base_url=config.KIMI_API_URL
        )

        # 3. Doubao
        self.client_doubao = OpenAI(
            api_key=config.VOLCENGINE_API_KEY,
            base_url=config.VOLCENGINE_API_URL
        )

        # 优化后的 Prompt
        self.system_prompt = """
### 角色定义
你是一个经验丰富的药学审题专家，负责对用户给出的题目进行审核

### 核心指令
请仔细阅读题目、选项、答案和解析，运用你的专业知识进行判断
正确：如果题目的答案和解析都正确，则题目判断为正确
错误：如果题目无法选出正确选项，或解析和答案不匹配，解析错误等，则题目判断为错误
如果有错别字，不算题目错误，但是要在【审题总结】模块进行说明

### 回答格式
输出必须严格按照以下格式：
【题目是否正确】正确 / 错误

【审题总结】
(简要说明题目的考点，依据检索结果判断答案是否准确)
(错误的话，要说明判断错误的原因)

【选项验证】
*[选项A]*：正确/错误
*[依据]*：(知识库中可以支撑选项正确或者错误的依据，最好来自教材或书籍)
*[分析]*：(你对这个选项的分析过程)
*[选项B]*：...
...

【解析修正建议】
(如果原解析有误或不完整，请在此补充；如果原解析完美，则写“无”。)
"""

    def _get_question_text(self, question_id: int):
        sql = "SELECT * FROM pharmacist_questions WHERE question_id = %s"
        data = db.execute_query(sql, (question_id,), fetch_one=True)
        if not data: return None

        options = ""
        valid_opts = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l']
        for char in valid_opts:
            key = f'option_{char}'
            if data.get(key):
                options += f"{char.upper()}.{data[key]}\n"

        # 增加案例背景
        case_info = ""
        if data.get('case_content') and str(data['case_content']).strip():
            case_info = f"【共用题干/案例背景】\n{data['case_content']}\n\n"

        return f"请校验以下题目：\n{case_info}【问题】{data['stem']}\n【选项】\n{options}\n【答案】{data['answer']}\n【解析】{data['analysis']}"

    def _save_review_result(self, q_id, ai_name, content):
        """解析 AI 回复并存入数据库"""
        # 清洗 <think>
        clean_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

        review_result = "需人工确认"

        if "【题目是否正确】正确" in clean_content or "【题目是否正确】: 正确" in clean_content:
            review_result = "通过"
        elif "【题目是否正确】错误" in clean_content or "【题目是否正确】: 错误" in clean_content:
            review_result = "驳回"
        elif "【结论】正确" in clean_content:
            review_result = "通过"
        elif "【结论】错误" in clean_content:
            review_result = "驳回"

        print(f"💾 保存 [{ai_name}] 审核结果: {review_result}")

        # ✅ 修复：SQL 增加 review_time 字段
        sql = """
        INSERT INTO question_review_details 
        (question_id, ai_name, review_result, review_content, rag_index, review_time)
        VALUES (%s, %s, %s, %s, %s, NOW())
        """

        try:
            db.execute_update(sql, (q_id, ai_name, review_result, clean_content, ""))
            return {"status": "success", "result": review_result, "content": clean_content}
        except Exception as e:
            print(f"❌ 数据库写入失败: {e}")
            return {"status": "error", "msg": f"数据库错误: {str(e)}"}

    def review_by_qwen(self, question_id: int):
        print(f"\n🚀 [Qwen] 正在审核题目 ID: {question_id} ...")
        q_text = self._get_question_text(question_id)
        if not q_text: return {"status": "error", "msg": "题目不存在"}

        try:
            resp = self.client_qwen.chat.completions.create(
                model=config.DASHSCOPE_MODEL,
                messages=[{"role": "system", "content": self.system_prompt}, {"role": "user", "content": q_text}],
                temperature=0.1
            )
            content = resp.choices[0].message.content
            return self._save_review_result(question_id, "Qwen", content)
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def review_by_kimi(self, question_id: int):
        print(f"\n🚀 [Kimi] 正在审核题目 ID: {question_id} ...")
        q_text = self._get_question_text(question_id)
        if not q_text: return {"status": "error", "msg": "题目不存在"}

        try:
            resp = self.client_kimi.chat.completions.create(
                model=config.KIMI_MODEL,
                messages=[{"role": "system", "content": self.system_prompt}, {"role": "user", "content": q_text}],
                temperature=0.1
            )
            content = resp.choices[0].message.content
            return self._save_review_result(question_id, "Kimi", content)
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def review_by_doubao(self, question_id: int):
        print(f"\n🚀 [Doubao] 正在审核题目 ID: {question_id} ...")
        q_text = self._get_question_text(question_id)
        if not q_text: return {"status": "error", "msg": "题目不存在"}

        try:
            resp = self.client_doubao.chat.completions.create(
                model=config.VOLCENGINE_MODEL,
                messages=[{"role": "system", "content": self.system_prompt}, {"role": "user", "content": q_text}],
                temperature=0.1
            )
            content = resp.choices[0].message.content
            return self._save_review_result(question_id, "Doubao", content)
        except Exception as e:
            return {"status": "error", "msg": str(e)}


other_ai = OtherAIReviewer()