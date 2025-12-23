import sys
import os
import json
import random
import string
from typing import List, Dict, Any, Generator

# === 1. 路径与环境配置 ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# === 2. 导入所有 Agent 和工具 ===
try:
    from backend.question_agent.a_question_tool import QuestionToolbox
    from backend.question_agent.b_questing_agent import QuestingAgent
    from backend.question_agent.c_distraction_agent import DistractionAgent
    from backend.question_agent.d_final_agent import FinalizationAgent
except ImportError as e:
    print(f"❌ 关键模块导入失败: {e}")
    sys.exit(1)


class QuestionPipeline:
    def __init__(self):
        self.questing_agent = QuestingAgent()
        self.distraction_agent = DistractionAgent()
        self.final_agent = FinalizationAgent()

    def _get_required_distractors(self, total: int, correct: int) -> int:
        """计算所需的干扰项数量"""
        return max(0, total - correct)

    def generate_full_question(self, params: Dict) -> Generator[Dict[str, Any], None, None]:
        """
        主流程：
        1. Agent B 生成案例和 N 道题目核心。
        2. 循环：对每一道题调用 Agent C (干扰项) 和 Agent D (审核)。
        3. 逐个返回最终结果。
        """

        # [0] 初始化参数
        topic = params.get('topic', '医学问题')
        q_type = params.get('type', 'A型题')
        total_options = params.get('total_count', 5)
        correct_options_count = params.get('correct_count', 1)
        q_count_req = params.get('question_count', 1)  # 请求生成的题目数量

        distractor_count = self._get_required_distractors(total_options, correct_options_count)

        # 核心数据容器
        questions_list = []  # 存储 Agent B 生成的所有题目核心
        case_content_global = ""  # 存储公共案例

        # =================================================================
        # [1] Stage 1: Agent B (一次性生成案例和所有题干)
        # =================================================================
        yield {"stage": "Generation", "status": "running", "message": f"➡️ 开始构思案例并生成 {q_count_req} 道题干..."}

        try:
            generator = self.questing_agent.generate_stream(params)
            b_output_json_str = None

            for chunk in generator:
                if isinstance(chunk, dict):
                    # 捕获最终 JSON 字符串
                    if chunk.get("type") == "final_json_string":
                        b_output_json_str = chunk["content"]
                    # 转发思考过程
                    elif chunk.get("type") == "process":
                        yield {"stage": "Generation", "stream": chunk["content"]}
                elif isinstance(chunk, str):
                    yield {"stage": "Generation", "stream": chunk}

            if b_output_json_str:
                # 清洗 JSON
                clean_json = b_output_json_str.replace("```json", "").replace("```", "").strip()
                parsed_b = json.loads(clean_json)

                # 提取公共案例
                case_content_global = parsed_b.get('case_content', '')

                # 提取题目列表
                if parsed_b.get('questions') and isinstance(parsed_b['questions'], list):
                    questions_list = parsed_b['questions']
                    yield {"stage": "Generation", "stream": f"\n✅ 成功生成 {len(questions_list)} 道题干核心。\n"}
                else:
                    raise ValueError("Agent B 返回数据中没有有效的 questions 列表")
            else:
                raise ValueError("Agent B 未返回有效数据")

        except Exception as e:
            yield {"stage": "Generation", "status": "error", "message": f"❌ Agent B 阶段失败: {str(e)}"}
            return

        # =================================================================
        # [循环处理] 对每一道题分别进行：干扰项生成 -> 最终审核
        # =================================================================

        total_q = len(questions_list)

        for idx, q_core in enumerate(questions_list, 1):
            prefix = f"[第 {idx}/{total_q} 题]"

            # --- [2] Agent C: 生成干扰项 (针对当前这一题) ---
            distraction_input = {
                "topic": topic,
                "stem": q_core.get('stem', ''),
                "correct_options": q_core.get('correct_options', []),
                "distractor_count": distractor_count,
                "analysis_overall": q_core.get('knowledge_ref', '')
            }

            yield {"stage": "Distraction", "status": "running", "message": f"➡️ {prefix} 正在生成干扰项..."}

            distractor_data = {}
            try:
                generator = self.distraction_agent.generate_stream(distraction_input)
                c_output_json_str = None

                for chunk in generator:
                    if isinstance(chunk, dict):
                        if chunk.get("type") == "final_json_string":
                            c_output_json_str = chunk["content"]
                        elif chunk.get("type") == "process":
                            # 给日志加前缀，区分是哪道题
                            yield {"stage": "Distraction", "stream": f"{prefix} {chunk['content']}"}
                    elif isinstance(chunk, str):
                        yield {"stage": "Distraction", "stream": f"{prefix} {chunk}"}

                if c_output_json_str:
                    clean_json = c_output_json_str.replace("```json", "").replace("```", "").strip()
                    distractor_data = json.loads(clean_json)
                else:
                    yield {"stage": "Distraction", "stream": f"\n⚠️ {prefix} Agent C 未返回有效 JSON，使用空干扰项。\n"}

            except Exception as e:
                yield {"stage": "Distraction", "status": "error", "message": f"❌ {prefix} 干扰项生成失败: {str(e)}"}
                continue  # 跳过这道题，继续下一道

            # 提取干扰项列表
            final_distractors = []
            raw_dist_list = distractor_data.get('distractors', [])
            for item in raw_dist_list:
                if isinstance(item, dict):
                    final_distractors.append(item.get('content', ''))
                elif isinstance(item, str):
                    final_distractors.append(item)
                else:
                    final_distractors.append(str(item))

            final_analysis = distractor_data.get('analysis_overall', '')

            # --- [3] Agent D: 终审与格式化 (针对当前这一题) ---
            final_audit_data = {
                "topic": topic,
                "question_type": q_type,
                "case_content": case_content_global,  # 使用公共案例
                "stem": q_core.get('stem', ''),
                "correct_options": q_core.get('correct_options', []),
                "distractors": final_distractors,
                "knowledge_ref": q_core.get('knowledge_ref', ''),
                "analysis_overall": final_analysis
            }

            yield {"stage": "Finalization", "status": "running", "message": f"➡️ {prefix} 最终审核..."}

            final_db_record = None
            final_status = "FAIL"

            try:
                generator = self.final_agent.process_question(final_audit_data)

                for chunk in generator:
                    if isinstance(chunk, dict):
                        if chunk.get('final_data'):
                            final_db_record = chunk.get('final_data')
                            final_status = chunk.get('audit_status')
                            break

                            # 打印思考
                        log = chunk.get('log') or chunk.get('thought')
                        if log:
                            yield {"stage": "Finalization", "stream": f"{prefix} {log}"}
                        elif chunk.get('error'):
                            yield {"stage": "Finalization", "stream": f"❌ {prefix} Agent D 报错: {chunk['error']}"}

            except Exception as e:
                yield {"stage": "Finalization", "status": "error", "message": f"❌ {prefix} 终审失败: {str(e)}"}
                continue

            # --- [4] 输出单题结果 ---
            if final_db_record:
                # 补全案例 (双重保险)
                if case_content_global:
                    final_db_record['case_content'] = case_content_global

                msg = f"✅ {prefix} 生成成功" if final_status == "PASS" else f"⚠️ {prefix} 需人工复核"
                yield {"completion": final_status, "message": msg, "data": final_db_record}
            else:
                yield {"stage": "Finalization", "status": "error", "message": f"❌ {prefix} 未能获取最终数据"}

        # 所有题目循环结束
        yield {"stage": "Done", "status": "final", "message": "🎉 所有题目处理完毕"}


if __name__ == "__main__":
    # 单元测试
    test_params = {
        "topic": "地西泮 中毒",
        "type": "案例分析题",
        "correct_count": 1,
        "total_count": 5,
        "has_case": True,
        "question_count": 2  # 测试生成2道题
    }
    print("🚀 开始测试...")
    for res in QuestionPipeline().generate_full_question(test_params):
        if res.get("stream"): print(res["stream"], end="")
        if res.get("completion"):
            print(f"\n>>> 结果: {res['message']}")
            print(json.dumps(res['data'], indent=2, ensure_ascii=False))