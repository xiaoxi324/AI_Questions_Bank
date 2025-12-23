/**
 * batch_review.js - 批量审题前端逻辑 (V2.0 单任务覆盖版)
 */

// ================= 全局配置 =================
const API = {
    START: '/api/batch/start',
    STOP: '/api/batch/stop',
    PROGRESS: '/api/batch/progress'
};

// 状态对应的 CSS 类名和文本 (对应 common.css)
const STATUS_CONFIG = {
    'WAIT':  { css: 'status-dot wait',    text: '等待' },
    'DOING': { css: 'status-dot loading', text: '处理中' },
    'DONE':  { css: 'status-dot pass',    text: '已完成' },
    'ERROR': { css: 'status-dot fail',    text: '错误' },
    'SKIP':  { css: 'status-dot',         text: '-' } // 未选中的AI
};

// 全局状态管理
const state = {
    isTaskActive: false, // 是否有任务数据显示在界面上
    timer: null,         // 轮询定时器
    page: 1,             // 当前页码
    pageSize: 20,        // 每页条数
    total: 0             // 总任务数
};

// ================= 初始化 =================

// ================= 初始化 =================

document.addEventListener('DOMContentLoaded', () => {
    // 【关键修复】安全检查：如果当前页面没有 "btn-batch-toggle" 元素，
    // 说明这不是批量审题页面，直接退出，防止报错。
    const btn = document.getElementById('btn-batch-toggle');
    if (!btn) return;

    // 1. 绑定全局函数
    window.toggleBatchTask = handleToggleBtn;
    window.changeBatchPage = handleChangePage;

    // 2. 页面加载时，立即检查是否有存量任务
    fetchProgress(true);
});
// ================= 核心交互逻辑 =================

async function handleToggleBtn() {
    const btn = document.getElementById('btn-batch-toggle');

    // 如果当前界面显示有任务 (isTaskActive = true)
    // 按钮功能变为 "停止/重置"
    if (state.isTaskActive) {
        if (!confirm("⚠️ 警告：\n确定要停止当前任务并清空进度吗？\n\n这会停止所有正在运行的 AI 线程，但已保存的审题记录不会丢失。")) {
            return;
        }
        await stopBatchTask();
    } else {
        // 如果当前是空闲状态
        // 按钮功能为 "开始新任务"
        await startBatchTask();
    }
}

async function startBatchTask() {
    // 1. 获取参数
    const startId = parseInt(document.getElementById('batch-start-id').value);
    const endId = parseInt(document.getElementById('batch-end-id').value);

    const aiList = [];
    if(document.getElementById('check-dingchun').checked) aiList.push('dingchun');
    if(document.getElementById('check-qwen').checked) aiList.push('qwen');
    if(document.getElementById('check-kimi').checked) aiList.push('kimi');
    if(document.getElementById('check-doubao').checked) aiList.push('doubao');

    // 2. 校验
    if (!startId || !endId || startId > endId) return alert("请输入有效的起始和结束题号");
    if (aiList.length === 0) return alert("请至少选择一个 AI 模型");

    // 3. UI 锁定
    const btn = document.getElementById('btn-batch-toggle');
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> 初始化中...';

    try {
        // 4. 发送请求
        const res = await fetch(API.START, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                start_id: startId,
                end_id: endId,
                ai_list: aiList
            })
        });
        const data = await res.json();

        if (data.status === 'success') {
            // 成功启动
            state.page = 1;
            state.isTaskActive = true;

            // 立即开启轮询
            startPolling();
            // 立即刷新一次数据
            fetchProgress();

            alert(`✅ 任务已启动！\n系统已自动跳过历史记录中已完成的题目。`);
        } else {
            alert("启动失败: " + data.msg);
            state.isTaskActive = false;
            updateUIState(false);
        }
    } catch (e) {
        console.error(e);
        alert("网络请求错误");
        state.isTaskActive = false;
        updateUIState(false);
    } finally {
        btn.disabled = false;
    }
}

async function stopBatchTask() {
    try {
        // 调用后端停止接口 (停止线程)
        await fetch(API.STOP, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: true })
        });

        // 前端停止轮询
        stopPolling();

        // 标记为不活跃，允许开始新任务
        // 注意：这里我们可以选择清空表格，或者保留表格让用户看到最后状态
        // 为了体验，我们保留表格，但解锁按钮让用户可以覆盖
        state.isTaskActive = false;
        updateUIState(false);

        document.getElementById('task-status-msg').innerText = "任务已停止 (点击开始可覆盖)";
        document.getElementById('task-status-msg').style.color = "#ff4d4f";

    } catch (e) {
        alert("停止请求失败");
    }
}

// ================= 数据轮询与渲染 =================

function startPolling() {
    if (state.timer) clearInterval(state.timer);
    // 每 1.5 秒轮询一次
    state.timer = setInterval(() => fetchProgress(), 1500);
}

function stopPolling() {
    if (state.timer) {
        clearInterval(state.timer);
        state.timer = null;
    }
}

async function fetchProgress(isFirstLoad = false) {
    try {
        // 请求 API 获取当前进度表数据
        const url = `${API.PROGRESS}?page=${state.page}&page_size=${state.pageSize}`;
        const res = await fetch(url);
        const json = await res.json();

        if (json.status === 'success') {
            state.total = json.total;

            // 逻辑判定：
            // 如果后端 batch_task_progress 表里有数据 (total > 0)，说明系统处于“任务模式”
            if (state.total > 0) {
                if (!state.isTaskActive) {
                    state.isTaskActive = true;
                    // 如果是首次加载发现有任务，或者中途发现有任务，开启轮询
                    startPolling();
                }
                updateUIState(true);
                renderTable(json.rows);
                renderStats(state.total, json.stats);
                renderPagination();
            } else {
                // 表里没数据 (可能是被 truncate 了)
                state.isTaskActive = false;
                stopPolling();
                updateUIState(false);
                renderTable([]); // 清空表格
            }
        }
    } catch (e) {
        console.error("轮询失败:", e);
    }
}

// ================= UI 渲染细节 =================

function updateUIState(active) {
    const btn = document.getElementById('btn-batch-toggle');
    const statusMsg = document.getElementById('task-status-msg');

    // 【关键修复】如果找不到元素，直接返回，不报错
    if (!btn || !statusMsg) return;

    const inputs = document.querySelectorAll('#range-control input, #ai-control input');

    if (active) {
        // ... 原有逻辑不变 ...
        btn.innerHTML = '<span>⏹</span> 停止 / 重置任务';
        btn.style.backgroundColor = '#ff4d4f';
        statusMsg.innerText = "🔥 任务进行中...";
        statusMsg.style.color = "#1890ff";
        inputs.forEach(input => input.disabled = true);
    } else {
        // ... 原有逻辑不变 ...
        btn.innerHTML = '<span>🚀</span> 开始批量审题';
        btn.style.backgroundColor = '#1890ff';
        if (state.total === 0) {
            statusMsg.innerText = "准备就绪";
            statusMsg.style.color = "#666";
        }
        inputs.forEach(input => input.disabled = false);
    }
}

function renderTable(rows) {
    const tbody = document.getElementById('batch-list-body');
    tbody.innerHTML = '';

    if (!rows || rows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-table-tip">暂无任务数据，请设置范围并点击「开始」</td></tr>';
        return;
    }

    const aiKeys = ['dingchun', 'qwen', 'kimi', 'doubao'];

    rows.forEach(row => {
        const tr = document.createElement('tr');
        tr.className = 'batch-row';

        // 题干预览 (处理可能为空的情况)
        const stemText = row.stem_preview ? `${row.stem_preview}...` : '(内容加载中...)';

        let html = `
            <td><strong>${row.question_id}</strong></td>
            <td style="color:#666; font-size:12px;">${stemText}</td>
        `;

        // 渲染 4 个 AI 的状态列
        aiKeys.forEach(key => {
            const statusKey = row[`${key}_status`] || 'WAIT';
            const config = STATUS_CONFIG[statusKey] || STATUS_CONFIG['WAIT'];

            // 样式处理：SKIP 显示为半透明，DONE 显示明显
            let style = "";
            if (statusKey === 'SKIP') style = "opacity: 0.3;";
            if (statusKey === 'DOING') style = "font-weight: bold; background-color: #f0f7ff;";

            html += `
                <td style="text-align: center; vertical-align: middle; ${style}">
                    <div style="display:inline-flex; align-items:center; justify-content:center;">
                        <span class="${config.css}"></span>
                        <span style="font-size:12px; margin-left:6px;">${config.text}</span>
                    </div>
                </td>
            `;
        });

        tr.innerHTML = html;
        tbody.appendChild(tr);
    });
}

function renderStats(total, stats) {
    // 更新右上角卡片
    // 显示逻辑：已完成 (所有AI完成数之和 / AI数量) 或者 简单显示定春进度
    // 这里为了直观，显示：[定春完成数] / [总题数] (作为主进度参考)

    // 1. 进度详情文本
    const details = [];
    const labels = { 'dingchun': '定春', 'qwen': 'Qwen', 'kimi': 'Kimi', 'doubao': '豆包' };

    let maxDone = 0; // 记录完成最多的那个，用来算进度条

    for (const [key, label] of Object.entries(labels)) {
        const count = stats[key] || 0;
        if (count > maxDone) maxDone = count;
        details.push(`${label}: ${count}`);
    }
    document.getElementById('ai-progress-details').innerText = details.join('  |  ');

    // 2. 主大字进度 (显示完成度最高的那个 / 总数)
    document.getElementById('batch-progress').innerText = `${maxDone} / ${total}`;
}

function renderPagination() {
    document.getElementById('batch-current-count').innerText = state.pageSize;
    document.getElementById('batch-total-count').innerText = state.total;
    document.getElementById('batch-current-page').innerText = state.page;

    const maxPage = Math.ceil(state.total / state.pageSize) || 1;
    document.getElementById('batch-total-page').innerText = maxPage;

    document.getElementById('batch-prev-page').disabled = (state.page <= 1);
    document.getElementById('batch-next-page').disabled = (state.page >= maxPage);
}

// ================= 翻页逻辑 =================

function handleChangePage(type) {
    const maxPage = Math.ceil(state.total / state.pageSize) || 1;

    if (type === 'prev' && state.page > 1) {
        state.page--;
        fetchProgress(); // 手动刷新一次
    } else if (type === 'next' && state.page < maxPage) {
        state.page++;
        fetchProgress(); // 手动刷新一次
    }
}