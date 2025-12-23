import os
import sys
import json
import re
import time
from openai import OpenAI

# 路径修复
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from config import config
from backend.tools.tools_sql_connect import db
from backend.tools.global_context import log_queue_ctx


def repair_json(json_str):
    json_str = re.sub(r'```json\s*', '', json_str)
    json_str = re.sub(r'```', '', json_str)
    return json_str.strip()


def emit(msg):
    print(msg)
    q = log_queue_ctx.get()
    if q: q.put(f"LOG: {msg}")


# === 状态机 ===
class ReadingState:
    def __init__(self):
        self.levels = {f"L{i}": "" for i in range(1, 9)}

    def _normalize_key(self, k):
        # 将 l1, L-1, Level1 统一洗成 L1
        match = re.search(r'(\d+)', str(k))
        if match:
            n = int(match.group(1))
            if 1 <= n <= 8: return f"L{n}"
        return None

    def update(self, item: dict):
        itype = item.get("type", "").lower()

        # 1. 尝试从 item 中提取显式的 level 定义
        # 有时候 AI 会在 title 里写 level，有时候会在 content 里写 level
        raw_level_key = item.get("level") or item.get("Level")
        norm_key = self._normalize_key(raw_level_key)

        # 提取标题内容：优先用 content (如果是title类型)，其次用 title 字段
        title_text = item.get("content") if itype == "title" else item.get("title")

        # 逻辑 A: 这是一个明确的标题节点
        if itype == "title" and norm_key and title_text:
            self.levels[norm_key] = title_text
            # 清空子层级
            try:
                idx = int(norm_key.replace("L", ""))
                for i in range(idx + 1, 9): self.levels[f"L{i}"] = ""
            except:
                pass
            print(f"🔄 [状态更新] 捕获标题: {norm_key} = {title_text}")

        # 逻辑 B: 这是一个内容节点，但 AI 顺便带了层级信息 (兼容性增强)
        elif itype == "content":
            # 检查是否有 L1...L8 字段
            for i in range(1, 9):
                k = f"L{i}"
                if item.get(k):
                    self.levels[k] = item[k]
                    print(f"🔄 [隐式更新] Content 携带: {k} = {item[k]}")

            # 检查是否有 level 字段
            if norm_key and title_text:
                # 这种情况比较少见，content 既然有 level，说明它可能既是标题又是内容
                # 我们选择信任它更新层级
                self.levels[norm_key] = title_text

    def get_levels(self):
        return self.levels.copy()

    def get_context_str(self):
        ctx = []
        for i in range(1, 9):
            v = self.levels[f"L{i}"]
            if v: ctx.append(f"L{i}:{v}")
        return " > ".join(ctx) if ctx else "无(根节点)"


def execute_process_task(book_id: int):
    emit(f"🧠 [处理] 开始 BookID={book_id}")

    # 获取书本信息
    book = db.execute_query("SELECT * FROM import_books WHERE book_id=%s", (book_id,), fetch_one=True)
    if not book: return {"status": "error", "msg": "书本不存在"}

    batch_size = book.get('batch_size', 15) or 15

    # 初始化 AI 客户端
    ai_model = config.LOCAL_CHAT_MODEL
    client = OpenAI(base_url=config.LOCAL_OPENAI_URL_CHAT, api_key="lm-studio")
    if "kimi" in ai_model.lower():
        client = OpenAI(base_url=config.KIMI_API_URL, api_key=config.KIMI_API_KEY)
    elif "doubao" in ai_model.lower():
        client = OpenAI(base_url=config.VOLCENGINE_API_URL, api_key=config.VOLCENGINE_API_KEY)

    state = ReadingState()

    # === Prompt ===
    # 这里的 Prompt 强调了 JSON 格式和层级识别
    system_prompt = """
你是一个药学文档解析引擎。任务：读取文本，拆解为 JSON 列表。

### 必须输出的 JSON 结构：
1. **标题节点** (当遇到章节、药物名、属性词时)：
   {"type": "title", "level": "L1", "content": "第一章 抗生素"}
   {"type": "title", "level": "L3", "content": "青霉素钠"}
   {"type": "title", "level": "L4", "content": "【适应证】"}
   *(注意：遇到新标题时，必须输出 title 类型，这决定了后续内容的层级归属)*

2. **内容节点** (正文描述)：
   {"type": "content", "content": "本品主要用于...", "combo_title": "青霉素 适应证"}

### 层级定义：
- L1/L2: 章、节
- L3/L4: 药物名称、疾病名称
- L5/L6: 【性状】、【适应证】、【用法用量】等属性标题
- L7/L8: 细分点
"""

    while True:
        # 1. 拿数据
        segments = db.execute_query(
            "SELECT * FROM book_segments WHERE book_id=%s AND is_processed=0 ORDER BY segment_order ASC LIMIT %s",
            (book_id, batch_size)
        )
        if not segments:
            emit("✅ 全部处理完毕")
            break

        segment_ids = [s['segment_id'] for s in segments]
        seg_range = f"{segments[0]['segment_order']}-{segments[-1]['segment_order']}"

        # 2. 构造输入
        input_text = "\n".join([s['content'].strip() for s in segments if s['content'].strip()])
        context_str = state.get_context_str()

        emit(f"🚀 [AI请求] 范围: {seg_range} | 上下文: {context_str}")

        try:
            # 3. AI 调用
            resp = client.chat.completions.create(
                model=ai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"【当前上下文】{context_str}\n\n【待解析文本】\n{input_text}"}
                ],
                temperature=0.1
            )
            raw_res = resp.choices[0].message.content

            # === DEBUG: 打印 AI 原始返回 ===
            print(f"\n--- AI 原始返回 (前200字符) ---\n{raw_res[:200]}...\n-----------------------------")

            # 4. 解析 JSON
            clean_json = repair_json(re.sub(r'<think>.*?</think>', '', raw_res, flags=re.DOTALL))
            try:
                items = json.loads(clean_json)
                if not isinstance(items, list): items = [items]  # 容错
            except:
                # 暴力容错
                try:
                    items = json.loads(f"[{clean_json}]")
                except:
                    print("❌ JSON 解析彻底失败")
                    # 标记跳过
                    fmt = ','.join(['%s'] * len(segment_ids))
                    db.execute_update(f"UPDATE book_segments SET is_processed=-1 WHERE segment_id IN ({fmt})",
                                      tuple(segment_ids))
                    continue

            # 5. 入库
            conn = db.get_connection()
            with conn.cursor() as cursor:
                valid_cnt = 0
                for item in items:
                    # 更新状态
                    state.update(item)

                    # 只有 content 入库
                    if item.get("type") == "content":
                        # 获取当前内存中的层级
                        lvls = state.get_levels()

                        # === DEBUG: 打印入库前的关键数据 ===
                        # 如果这里全是空字符串，说明状态机没更新
                        # print(f"📝 准备入库: L1={lvls['L1']} | L3={lvls['L3']} | Content={item.get('content')[:20]}")

                        # 组合标题
                        combo = item.get("combo_title", "")
                        if not combo:
                            active = [v for k, v in lvls.items() if v]
                            combo = " / ".join(active[-3:][::-1]) if active else "未分类"

                        sql = """INSERT INTO knowledge_fragments 
                                (book_id, book_name, source_segment_range, 
                                 L1, L2, L3, L4, L5, L6, L7, L8, 
                                 combo_title, content, is_embedded)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)"""

                        params = (
                            book_id, book['book_name'], seg_range,
                            lvls['L1'], lvls['L2'], lvls['L3'], lvls['L4'],
                            lvls['L5'], lvls['L6'], lvls['L7'], lvls['L8'],
                            combo, item.get("content")
                        )

                        cursor.execute(sql, params)
                        valid_cnt += 1

                # 提交批次
                fmt = ','.join(['%s'] * len(segment_ids))
                cursor.execute(f"UPDATE book_segments SET is_processed=1 WHERE segment_id IN ({fmt})",
                               tuple(segment_ids))
                cursor.execute("UPDATE import_books SET processed_segments = processed_segments + %s WHERE book_id=%s",
                               (len(segments), book_id))
                conn.commit()
                emit(f"✅ 入库成功: {valid_cnt} 条")

        except Exception as e:
            emit(f"❌ 发生异常: {e}")
            time.sleep(1)

    db.execute_update("UPDATE import_books SET status='processed' WHERE book_id=%s", (book_id,))
    return {"status": "ok"}