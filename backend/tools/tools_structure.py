import json
import re
from openai import OpenAI
from config import config
from backend.tools.tools_sql_connect import db

# ================= 配置区域 =================
# 在这里指定结构化专用的模型 ID (必须与 LM Studio 加载的一致)，使用者根据自己的需要可以修改
STRUCTURE_MODEL_ID = "qwen3-vl-4b-thinking"


class StructureAgent:
    def __init__(self):
        print(f"🔌 [结构化助手] 正在连接独立配置模型: {STRUCTURE_MODEL_ID}")

        self.client = OpenAI(
            base_url=config.LOCAL_OPENAI_URL_CHAT,
            api_key="noneed",
        )
        self.model = STRUCTURE_MODEL_ID

        self.system_prompt = """
你是一个专业的**执业药师题目批量结构化专家**。
你的任务是将用户输入的文本，拆解为 JSON 数组。

### 严格要求：
1. **只输出 JSON**，不要输出任何其他解释性文字。
2. JSON 必须是一个**数组** `[...]`。
3. 数组中包含对象，字段如下：
   - "case_content": string (案例背景，若无则空)
   - "stem": string (题干)
   - "options": dict (选项 {"A": "...", "B": "..."})
   - "answer": string (正确答案)
   - "analysis": string (解析)
   - "question_type": string (单选题/多选题/配伍选择题)
"""

    def parse_and_save(self, raw_text: str, source: str = "智能录入"):
        """批量解析并入库"""
        try:
            print(f"🤖 [AI 思考] 正在调用 {self.model} 进行拆解...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"请处理以下文本：\n{raw_text}"}
                ],
                temperature=0.1
            )

            raw_content = response.choices[0].message.content

            # === 1. 清洗 <think> 标签 ===
            content_no_think = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()

            # === 2. 精准提取 JSON 数组 (寻找最外层 []) ===
            start_idx = content_no_think.find('[')
            end_idx = content_no_think.rfind(']')

            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                clean_json_str = content_no_think[start_idx: end_idx + 1]
                data_list = json.loads(clean_json_str)

                if isinstance(data_list, dict):
                    data_list = [data_list]

                print(f"🔍 AI 识别出 {len(data_list)} 道题目，准备入库...")

            else:
                print(f"❌ [解析失败] 未找到 JSON 数组标记 []。")
                print(f"❌ [清洗后内容]: {content_no_think[:200]}...")
                return {"status": "error", "msg": "AI 未返回有效的 JSON 数组格式"}

        except Exception as e:
            print(f"❌ AI 调用或处理失败: {e}")
            return {"status": "error", "msg": str(e)}

        # 4. 循环入库
        success_ids = []
        conn = db.get_connection()
        if not conn: return {"status": "error", "msg": "数据库连接失败"}

        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO pharmacist_questions 
                (question_type, case_content, stem, 
                 option_a, option_b, option_c, option_d, option_e, option_f,
                 option_g, option_h, option_i, option_j, option_k, option_l,
                 answer, analysis, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                # === 优化：共用题干自动填充 ===
                last_case_content = ""

                for item in data_list:
                    opts = item.get("options", {})
                    q_type = item.get("question_type", "单选题")

                    # 处理共用题干
                    current_case = item.get("case_content", "").strip()
                    if current_case:
                        last_case_content = current_case  # 更新缓存
                    else:
                        current_case = last_case_content  # 沿用上一题的案例

                    params = (
                        q_type,
                        current_case,
                        item.get("stem", ""),
                        opts.get("A"), opts.get("B"), opts.get("C"), opts.get("D"), opts.get("E"), opts.get("F"),
                        opts.get("G"), opts.get("H"), opts.get("I"), opts.get("J"), opts.get("K"), opts.get("L"),
                        item.get("answer", ""),
                        item.get("analysis", ""),
                        source
                    )
                    cursor.execute(sql, params)
                    success_ids.append(cursor.lastrowid)

                conn.commit()
                print(f"✅ 批量入库成功！共 {len(success_ids)} 条。")
                return {
                    "status": "success",
                    "count": len(success_ids),
                    "ids": success_ids,
                    "msg": f"成功识别并录入 {len(success_ids)} 道题目"
                }

        except Exception as e:
            conn.rollback()
            print(f"❌ 数据库写入失败: {e}")
            return {"status": "error", "msg": str(e)}
        finally:
            conn.close()


# 实例化 (供内部调用)
structure_agent = StructureAgent()


# ==================== 对外暴露的入口函数 ====================
def add_question_to_db(raw_text: str, source: str = "智能录入"):
    """
    [API入口] 供 main.py 调用，执行题目智能解析并入库。
    替代了原 utils.py 的功能。
    """
    if not raw_text:
        return {"status": "error", "msg": "输入内容为空"}

    # 委托给 agent
    return structure_agent.parse_and_save(raw_text, source)


# ==================== 测试代码 ====================
if __name__ == "__main__":
    # 模拟一段包含共用题干的复杂文本
    test_text = """
    【案例】患者男，60岁，高血压病史。
    1. 该患者首选的降压药是
    A. 硝苯地平 B. 普萘洛尔 C. 氢氯噻嗪
    答案：A 解析：钙通道阻滞剂适用老年高血压。

    2. 若患者出现踝部水肿，原因可能是
    A. 药物副作用 B. 肾衰竭 C. 心衰
    答案：A 解析：CCB类常见副作用。
    """

    print("-" * 50)
    print("🚀 开始测试结构化助手...")
    # 直接调用对外接口测试
    res = add_question_to_db(test_text, source="脚本测试")
    print(res)