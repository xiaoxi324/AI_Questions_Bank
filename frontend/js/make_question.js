/**
 * make_question.js - 智能编题功能前端逻辑 (多题适配版)
 */

let isStreaming = false;

function parseSSE(data) {
    if (!data.startsWith("data:")) return null;
    const jsonString = data.substring(5).trim();
    if (jsonString === "[DONE]") return { done: true };
    try {
        return JSON.parse(jsonString);
    } catch (e) { return null; }
}

async function startGeneration() {
    if (isStreaming) return;

    // ================== 1. 参数获取与修正 ==================
    const topic = document.getElementById('topic').value.trim();

    // 正确答案数量 (单选题=1, 多选题>1)
    const correctCount = parseInt(document.getElementById('correct_count').value) || 1;

    // [修正点1] 选项数量 (例如 A/B/C/D/E = 5个)
    // 之前叫 total_count 容易被误解为题目数量，这里为了兼容后端，我们改个变量名，但发给后端的字段要看后端定义
    // 假设后端 total_count 指的是选项数，那这里默认 5 没问题。
    // 但如果后端把 total_count 当成了题目数，这里就会出Bug。
    // 安全起见，我们读取名为 'option_count' 的输入框，如果没有，再尝试 'total_count'
    let optionCountInput = document.getElementById('option_count') || document.getElementById('total_count');
    const optionCount = optionCountInput ? parseInt(optionCountInput.value) : 5; // 默认5个选项(A-E)

    // [修正点2] 题目生成数量 (核心修复)
    // 优先读取 id="question_count" 的输入框，默认为 1
    const qCountInput = document.getElementById('question_count');
    const questionCount = qCountInput ? parseInt(qCountInput.value) : 1;

    const caseRadio = document.querySelector('input[name="has_case"]:checked');
    const hasCase = caseRadio ? (caseRadio.value === 'true') : true;

    if (!topic) { alert("请输入考点！"); return; }
    // =======================================================

    // 2. UI 初始化
    const logArea = document.getElementById('agent_log_area');
    const snippetArea = document.getElementById('snippet_area');
    const startBtn = document.getElementById('start_btn');
    const resultArea = document.getElementById('final_content');
    const placeholder = document.getElementById('result_placeholder');
    const statusTag = document.getElementById('status_tag');

    const resultFooter = document.getElementById('result_footer');
    if (resultFooter) resultFooter.style.display = 'none';

    logArea.innerHTML = '';
    snippetArea.innerHTML = '';
    resultArea.innerHTML = '';
    resultArea.style.display = 'block';

    if(placeholder) {
        placeholder.style.display = 'block';
        placeholder.textContent = `正在生成 ${questionCount} 道题目...`;
    }

    statusTag.textContent = '生成中...';
    statusTag.className = 'status-tag status-run';
    statusTag.style.color = 'orange';

    startBtn.disabled = true;
    startBtn.textContent = `⏳ 生成中 (${questionCount}题)...`;

    isStreaming = true;

    try {
        const response = await fetch('/api/generate/question', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                topic: topic,
                has_case: hasCase,
                correct_count: correctCount,

                // [关键修正]
                // 告诉后端：我们要生成的题目数量是 question_count
                // 告诉后端：每道题的选项数量是 optionCount (传给 total_count 以兼容旧后端逻辑，或者后端需要改一下接收字段)
                question_count: questionCount,
                total_count: optionCount
            })
        });

        // ... 后面的流式处理逻辑不变 ...
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop();

            for (const line of lines) {
                const parsed = parseSSE(line);
                if (!parsed) continue;
                if (parsed.done) break;

                if (parsed.type === 'process') {
                    let text = parsed.content || '';
                    if(text.includes('Agent')) text = `<span class="log-thought">${text}</span>`;
                    const div = document.createElement('div');
                    div.className = 'log-line';
                    div.innerHTML = text.replace(/\n/g, '<br>');
                    logArea.appendChild(div);
                    logArea.scrollTop = logArea.scrollHeight;
                }

                if (parsed.type === 'snippet') {
                    const div = document.createElement('div');
                    div.className = 'snip-block';
                    div.textContent = parsed.content;
                    snippetArea.appendChild(div);
                    snippetArea.scrollTop = snippetArea.scrollHeight;
                }

                if (parsed.type === 'error') {
                    logArea.innerHTML += `<div class="log-error" style="color:red">❌ ${parsed.content}</div>`;
                }

                if (parsed.completion) {
                    appendSingleQuestion(parsed.completion, parsed.data);
                }
            }
        }

    } catch (e) {
        alert("发生错误: " + e.message);
    } finally {
        isStreaming = false;
        startBtn.disabled = false;
        startBtn.textContent = '开始编题';
        statusTag.textContent = '生成完毕';
        statusTag.className = 'status-tag status-ok';
        statusTag.style.color = 'green';
        if(placeholder) placeholder.style.display = 'none';
    }
}

/**
 * 核心：向界面追加一道新生成的题目
 */
function appendSingleQuestion(status, data) {
    const resultContainer = document.getElementById('final_content');
    const placeholder = document.getElementById('result_placeholder');
    if(placeholder) placeholder.style.display = 'none';

    if (!data) return;

    // 1. 创建题目卡片容器
    const card = document.createElement('div');
    card.className = 'qa-card';
    card.style.borderBottom = '2px dashed #eee';
    card.style.padding = '15px 0';
    card.style.marginBottom = '15px';

    // 2. 构造选项 HTML
    let optionsHtml = '<ul class="qa-options" style="list-style:none; padding:0;">';
    ['a','b','c','d','e','f','g','h','i','j','k','l'].forEach(key => {
        const optionKey = `option_${key}`;
        const val = data[optionKey];
        if (val) {
            const isRight = data.answer && data.answer.includes(key.toUpperCase());
            const style = isRight ? 'color:green; font-weight:bold; background-color:#f6ffed; padding:2px 5px; border-radius:4px;' : '';
            optionsHtml += `<li style="margin-bottom:5px;">
                <span style="${style}">${key.toUpperCase()}. ${val}</span>
            </li>`;
        }
    });
    optionsHtml += '</ul>';

    // 3. 填充卡片内容
    // 注意：data 是一个对象，我们把它 stringify 后作为参数传给 onclick
    // 这里的 replace 是为了防止 json 里的引号破坏 HTML 属性
    const dataStr = JSON.stringify(data).replace(/"/g, '&quot;');

    card.innerHTML = `
        <div class="qa-item" style="margin-bottom:8px;">
            <strong style="color:#666;">案例:</strong>
            <span style="font-size:13px; color:#333;">${data.case_content || '(无)'}</span>
        </div>
        <div class="qa-item" style="margin-bottom:8px;">
            <strong style="color:#666;">题干:</strong>
            <span style="font-size:14px; font-weight:bold; color:#000;">${data.stem}</span>
        </div>
        ${optionsHtml}
        <div class="qa-item" style="margin-top:10px; padding-top:10px; border-top:1px dashed #eee;">
            <strong style="color:#666;">解析:</strong>
            <span style="font-size:12px; color:#555;">${data.analysis}</span>
        </div>
        <div class="action-bar" style="text-align:right; margin-top:10px;">
            <button class="btn-sub btn-save" style="background:#1890ff; color:white; border:none; padding:5px 15px; border-radius:4px; cursor:pointer;" onclick="saveSingleQuestion(this, ${dataStr})">存入题库</button>
        </div>
    `;

    // 4. 追加到容器
    resultContainer.appendChild(card);

    // 滚动到底部
    const scrollBox = document.getElementById('final_result_area');
    if(scrollBox) scrollBox.scrollTop = scrollBox.scrollHeight;
}

/**
 * 单题入库逻辑
 * @param {HTMLElement} btn 点击的按钮元素
 * @param {Object} data 题目数据
 */
async function saveSingleQuestion(btn, data) {
    if(!confirm("确定将此题目存入题库吗？")) return;

    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "入库中...";

    try {
        const res = await fetch('/api/question/save_to_db', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        const j = await res.json();

        if(j.status === 'success') {
            btn.textContent = "✅ 已入库";
            btn.style.backgroundColor = "#52c41a";
            btn.style.cursor = "default";
        } else {
            alert("❌ 失败: " + j.message);
            btn.disabled = false;
            btn.textContent = originalText;
        }
    } catch(e) {
        alert("网络错误");
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

// 暴露给全局
window.startGeneration = startGeneration;
window.saveSingleQuestion = saveSingleQuestion;