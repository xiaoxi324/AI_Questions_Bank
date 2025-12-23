/**
 * library.js - 题库管理与审题核心模块 (V6.0 终极版)
 */

// ================= 1. 题库列表逻辑 =================

window.initLibrary = function() {
    window.loadQuestionList();
}

// 加载列表
window.loadQuestionList = async function() {
    const tbody = document.getElementById('question-list-body');
    if(!tbody) return;

    const searchInput = document.getElementById('search-input');
    const searchText = searchInput ? searchInput.value.trim() : '';

    tbody.innerHTML = '<tr><td colspan="10" class="loading-text">🚀 数据加载中...</td></tr>';

    try {
        const res = await fetch('/api/data/question/list', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                page: window.currentPage,
                page_size: window.pageSize,
                search_text: searchText
            })
        });
        const data = await res.json();

        tbody.innerHTML = '';
        if(!data.data || data.data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="loading-text">暂无数据</td></tr>';
            return;
        }

        data.data.forEach(item => {
            const tr = document.createElement('tr');
            const statusHtml = (st) => `<div class="status-cell"><span class="status-dot ${window.getStatusClass(st)}"></span><span>${st||'未执行'}</span></div>`;

            tr.innerHTML = `
                <td>${item.question_id}</td>
                <td><span class="badge">${item.question_type}</span></td>
                <td class="text-truncate" title="${window.escapeHtml(item.stem)}">${window.escapeHtml(item.stem)}</td>
                <td class="font-bold">${window.escapeHtml(item.answer)}</td>
                <td>${item.source}</td>
                <td>${statusHtml(item.status_dingchun)}</td>
                <td>${statusHtml(item.status_qwen)}</td>
                <td>${statusHtml(item.status_kimi)}</td>
                <td>${statusHtml(item.status_doubao)}</td>
                <td>
                    <span class="btn-link" onclick="window.openModal(${item.question_id}, this, false)">查看</span>
                    <span class="btn-link delete" onclick="window.deleteQ(${item.question_id})">删除</span>
                </td>
            `;
            tr.dataset.json = JSON.stringify(item);
            tbody.appendChild(tr);
        });

        const pageInfo = document.getElementById('page-info');
        if(pageInfo) pageInfo.innerText = `第 ${data.page} 页 / 共 ${data.total} 条`;

    } catch(e) {
        console.error(e);
        if(tbody) tbody.innerHTML = `<tr><td colspan="10" class="error-text">加载失败: ${e.message}</td></tr>`;
    }
}

window.changePage = function(delta) {
    const newPage = window.currentPage + delta;
    if (newPage < 1) return;
    window.currentPage = newPage;
    window.loadQuestionList();
}

window.deleteQ = async function(id) {
    if(!confirm(`确定要永久删除题目 ID:${id} 吗？`)) return;
    try {
        await fetch('/api/data/question/manage', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: "delete", payload: { id: id } })
        });
        window.loadQuestionList();
    } catch(e) { alert("删除失败: " + e); }
}

// ================= 2. 弹窗与审题逻辑 =================

window.openModal = function(id, btn, autoStart = false) {
    window.currentQId = id;
    const modal = document.getElementById('common-modal');
    if(!modal) return;
    modal.classList.remove('hidden');

    let data;
    if (btn) {
        try {
            const tr = btn.closest('tr');
            data = JSON.parse(tr.dataset.json);
        } catch(e){}
    }

    if(data) {
        document.getElementById('modal-id').innerText = data.question_id;

        const caseBox = document.getElementById('modal-case-content');
        if (data.case_content && data.case_content.trim() !== "" && data.case_content !== "None") {
            caseBox.innerText = data.case_content;
            caseBox.style.display = "block";
        } else {
            caseBox.style.display = "none";
        }

        document.getElementById('modal-stem').innerText = data.stem;
        document.getElementById('modal-options').innerText = data.options_display || '无选项';
        document.getElementById('modal-answer').innerText = data.answer;
        document.getElementById('modal-analysis').innerText = data.analysis || '暂无';
    }

    window.resetTabs();
    window.switchTab('dingchun');
    window.fetchReviewHistory(id);

    if (autoStart) {
        window.startAllReviews();
    }
}

window.closeModal = function() {
    document.getElementById('common-modal').classList.add('hidden');
}

window.resetTabs = function() {
    ['dingchun', 'qwen', 'kimi', 'doubao'].forEach(key => {
        const md = document.getElementById(`md-${key}`);
        if(md) md.innerHTML = '<div class="empty-state">暂无记录</div>';

        const st = document.getElementById(`status-text-${key}`);
        if(st) st.innerText = '未执行';

        const dt = document.getElementById(`dot-${key}`);
        if(dt) dt.className = 'status-dot wait';

        const sel = document.getElementById(`history-select-${key}`);
        if(sel) { sel.innerHTML = '<option>暂无历史</option>'; sel.disabled = true; }

        if(key==='dingchun') {
            const rb = document.getElementById('rag-box-dingchun');
            if(rb) rb.classList.add('hidden');
        }
    });
    window.currentHistoryCache = { dingchun: [], qwen: [], kimi: [], doubao: [] };
}

window.switchTab = function(tabName) {
    document.querySelectorAll('.tab-item').forEach(el => el.classList.remove('active'));
    const idx = {'dingchun':0, 'qwen':1, 'kimi':2, 'doubao':3}[tabName];
    if(document.querySelectorAll('.tab-item')[idx])
        document.querySelectorAll('.tab-item')[idx].classList.add('active');

    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    const content = document.getElementById(`tab-content-${tabName}`);
    if(content) content.classList.add('active');
}

window.fetchReviewHistory = async function(id) {
    try {
        const res = await fetch('/api/data/review/history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question_id: id })
        });
        const resp = await res.json();

        if (resp.status === 'success') {
            window.currentHistoryCache = resp.data;
            ['dingchun', 'qwen', 'kimi', 'doubao'].forEach(key => {
                window.initHistorySelect(key, resp.data[key]);
                if(resp.data[key]?.length) window.renderAiSingleRecord(key, resp.data[key][0]);
            });
        }
    } catch (e) { console.error(e); }
}

window.initHistorySelect = function(key, records) {
    const select = document.getElementById(`history-select-${key}`);
    if(!select) return;

    if (!records || records.length === 0) {
        select.innerHTML = '<option>暂无历史</option>';
        select.disabled = true;
        return;
    }

    let html = '';
    records.forEach((rec, index) => {
        const isLatest = index === 0 ? ' (最新)' : '';
        const timeStr = rec.review_time ? rec.review_time.substring(5, 16) : '未知';
        html += `<option value="${index}">${timeStr} [${rec.review_result}]${isLatest}</option>`;
    });

    select.innerHTML = html;
    select.disabled = false;

    select.onchange = (e) => {
        const record = window.currentHistoryCache[key][e.target.value];
        window.renderAiSingleRecord(key, record);
    };
}

window.renderAiSingleRecord = function(key, data) {
    if (!data) return;

    const statusMap = { '通过': 'pass', '驳回': 'fail', '需人工确认': 'warn' };
    const stateClass = statusMap[data.review_result] || 'warn';

    const st = document.getElementById(`status-text-${key}`);
    if(st) st.innerText = data.review_result;

    const dt = document.getElementById(`dot-${key}`);
    if(dt) dt.className = `status-dot ${stateClass}`;

    const md = document.getElementById(`md-${key}`);
    if(md) md.innerHTML = marked.parse(data.review_content);

    if (key === 'dingchun') {
        const ragBox = document.getElementById('rag-box-dingchun');
        const ragText = document.getElementById('rag-text-dingchun');
        if (ragBox && ragText) {
            if (data.rag_index) {
                ragBox.classList.remove('hidden');
                ragText.innerText = data.rag_index;
            } else {
                ragBox.classList.add('hidden');
            }
        }
    }
}

window.startAllReviews = function() {
    if(!window.currentQId) return;
    window.runReviewAgent(window.currentQId);
    window.runOtherAi(window.currentQId, 'qwen');
    window.runOtherAi(window.currentQId, 'kimi');
    window.runOtherAi(window.currentQId, 'doubao');
}

window.setLoadingState = function(key) {
    const st = document.getElementById(`status-text-${key}`);
    if(st) st.innerText = '运行中...';
    const dt = document.getElementById(`dot-${key}`);
    if(dt) dt.className = 'status-dot loading';

    const md = document.getElementById(`md-${key}`);
    if (key === 'dingchun' && md) {
        // 浅色日志框
        md.innerHTML = `
            <div class="log-container" style="background:#f0f7ff; color:#333; padding:15px; border-radius:6px; font-family:'Menlo', monospace; font-size:12px; height:200px; overflow-y:auto; border:1px solid #bae7ff; line-height:1.5;">
                <div style="color:#1890ff; font-weight:bold; margin-bottom:5px;">> 🚀 正在连接定春大脑...</div>
            </div>`;
    } else if(md) {
        md.innerHTML = '<div class="loading-wrapper" style="text-align:center; padding:40px;"><div class="loading-spinner" style="margin:0 auto;"></div><div style="margin-top:10px; color:#666;">AI 正在思考...</div></div>';
    }
}

window.runReviewAgent = async function(id) {
    window.setLoadingState('dingchun');
    const logBox = document.querySelector('#md-dingchun .log-container');

    try {
        const res = await fetch('/api/tool/review', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ai_type: 'dingchun', question_id: id })
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.trim()) continue;

                if (line.startsWith('LOG: ')) {
                    const msg = line.substring(5);
                    if (logBox) {
                        const div = document.createElement('div');
                        div.innerText = `> ${msg}`;
                        div.style.borderBottom = "1px dashed #e6f7ff";
                        div.style.marginBottom = "4px";
                        div.style.paddingBottom = "2px";
                        logBox.appendChild(div);
                        logBox.scrollTop = logBox.scrollHeight;
                    }
                } else if (line.startsWith('DATA: ')) {
                    const jsonStr = line.substring(6);
                    try {
                        const data = JSON.parse(jsonStr);
                        if (data.status === 'success') {
                            const resultData = {
                                review_result: data.review_result,
                                review_time: '刚刚',
                                review_content: data.review_content,
                                rag_index: data.rag_context
                            };
                            window.renderAiSingleRecord('dingchun', resultData);
                            window.fetchReviewHistory(id);
                        } else {
                            window.showAiError('dingchun', data.msg);
                        }
                    } catch (e) { window.showAiError('dingchun', "结果解析失败"); }
                }
            }
        }
    } catch(e) { window.showAiError('dingchun', e.message); }
}

window.runOtherAi = async function(id, type) {
    window.setLoadingState(type);
    try {
        const res = await fetch('/api/tool/review', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ai_type: type, question_id: id })
        });
        const data = await res.json();
        if(data.status === 'success') {
             const resultData = {
                review_result: data.result,
                review_time: '刚刚',
                review_content: data.content
            };
            window.renderAiSingleRecord(type, resultData);
            window.fetchReviewHistory(id);
        } else {
            window.showAiError(type, data.msg);
        }
    } catch(e) { window.showAiError(type, e.message); }
}

window.showAiError = function(key, msg) {
    const st = document.getElementById(`status-text-${key}`);
    if(st) st.innerText = '错误';
    const dt = document.getElementById(`dot-${key}`);
    if(dt) dt.className = 'status-dot fail';
    const md = document.getElementById(`md-${key}`);
    if(md) md.innerHTML = `<div class="error-text">❌ ${msg}</div>`;
}