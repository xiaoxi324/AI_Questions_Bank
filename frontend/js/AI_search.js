/**
 * AI_search.js - 智能对比前端逻辑
 */

const API_COMPARE = {
    GET_BOOK: '/api/smart_compare/get_book_content',
    PROCESS: '/api/smart_compare/process',
    BOOK_LIST: '/api/import/book/list' // <--- 修改这里，对应上面的后端接口
};

// ================= 初始化入口 =================

// 这是挂载到 window 上的初始化函数，命名保持风格一致
window.initAISearch = async function() {
    console.log("🚀 初始化智能对比模块...");
    await loadBookOptions();
}

// ================= 内部逻辑 =================

async function loadBookOptions() {
    const select = document.getElementById('compare-book-select');
    if (!select) return;

    try {
        const res = await fetch(API_COMPARE.BOOK_LIST, {
             method: 'POST',
             headers: {'Content-Type': 'application/json'},
             body: JSON.stringify({ page: 1, page_size: 100 })
        });
        const json = await res.json();

        if (json.status === 'success' && json.data) {
            let html = '<option value="">选择来源书本...</option>';
            json.data.forEach(book => {
                html += `<option value="${book.book_id}">${book.book_name}</option>`;
            });
            select.innerHTML = html;
        }
    } catch (e) {
        console.error("加载书本失败:", e);
    }
}

// 导出到全局的函数，供 HTML 中的 onclick 调用
window.importBookContent = async function() {
    const bookId = document.getElementById('compare-book-select').value;
    const startRow = document.getElementById('compare-start-row').value;
    const endRow = document.getElementById('compare-end-row').value;

    if (!bookId) return alert("请先选择一本书");
    if (!startRow || !endRow) return alert("请输入起始和结束行号");
    if (parseInt(startRow) > parseInt(endRow)) return alert("起始行号不能大于结束行号");

    const btn = document.getElementById('btn-import-book');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '📥 加载中...';

    try {
        const res = await fetch(API_COMPARE.GET_BOOK, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                book_id: parseInt(bookId),
                start_row: parseInt(startRow),
                end_row: parseInt(endRow)
            })
        });
        const json = await res.json();

        if (json.status === 'success') {
            const textarea = document.getElementById('compare-input');
            textarea.value = json.data;
            if(!json.data) alert("该范围内没有内容");
        } else {
            alert("导入失败: " + json.msg);
        }
    } catch (e) {
        console.error(e);
        alert("网络请求错误");
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

// 2. 开始智能分析 (流式版)
window.startSmartAnalysis = async function() {
    const text = document.getElementById('compare-input').value.trim();
    if (!text) return alert("请先输入或导入需要审核的文本内容");

    const container = document.getElementById('compare-results-body');
    const statusLabel = document.getElementById('analysis-status');
    const btn = document.getElementById('btn-start-analysis');

    // UI 初始化
    btn.disabled = true;
    btn.innerHTML = '⚡ 分析中...';
    // 保留 loading 占位，等第一条数据来了再清空，或者追加在后面
    container.innerHTML = `
        <div id="compare-loading" class="loading-placeholder" style="text-align:center; padding:20px;">
            <div class="loading-spinner"></div>
            <div style="margin-top:10px;">AI 正在逐行分析，结果将即时显示...</div>
        </div>
    `;
    statusLabel.innerText = "准备中...";

    try {
        const response = await fetch(API_COMPARE.PROCESS, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        });

        if (!response.ok) throw new Error("网络请求失败");

        // === 流式读取核心逻辑 ===
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = ""; // 缓存未读完的片段
        let count = 0;

        // 首次收到数据时，清空 loading
        let isFirst = true;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            // 解码二进制流并追加到缓存
            buffer += decoder.decode(value, { stream: true });

            // 按换行符切割 (NDJSON)
            let lines = buffer.split("\n");

            // 数组最后一块可能是不完整的，存回 buffer 等待下一次
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.trim()) continue;

                try {
                    const item = JSON.parse(line);

                    if (isFirst) {
                        container.innerHTML = ""; // 清空 loading
                        isFirst = false;
                        statusLabel.innerText = "正在输出...";
                    }

                    // 立即渲染这一条
                    appendResult(item, count++);

                    // 滚动到底部 (可选)
                    container.scrollTop = container.scrollHeight;

                } catch (err) {
                    console.error("JSON Parse Error:", err);
                }
            }
        }

        statusLabel.innerText = `完成 (共 ${count} 个片段)`;

    } catch (e) {
        console.error(e);
        container.innerHTML += `<div class="error-state">❌ 发生错误: ${e.message}</div>`;
        statusLabel.innerText = "异常终止";
    } finally {
        btn.disabled = false;
        btn.innerHTML = '⚡ 开始智能分析';
        const loading = document.getElementById('compare-loading');
        if(loading) loading.remove(); // 确保 loading 被移除
    }
}

// === 单条渲染函数 (追加模式) ===
function appendResult(item, index) {
    const container = document.getElementById('compare-results-body');

    const comp = item.comparison_result || {};
    // 获取后端返回的新状态字段，默认为 error 以防万一
    const status = comp.status || 'error';

    // === 定义三态样式映射 ===
    let styleConfig = {};

    switch (status) {
        case 'fully_consistent':
            styleConfig = {
                color: '#52c41a', // 绿色
                icon: '✅ 完全一致',
                borderColor: '#b7eb8f',
                bgColor: '#f6ffed'
            };
            break;
        case 'semantically_consistent':
            styleConfig = {
                color: '#faad14', // 黄色/橙色
                icon: '⚠️ 语义一致',
                borderColor: '#ffe58f',
                bgColor: '#fffbe6'
            };
            break;
        case 'error':
        default:
            styleConfig = {
                color: '#ff4d4f', // 红色
                icon: '❌ 错误/无依据',
                borderColor: '#ffa39e',
                bgColor: '#fff1f0'
            };
            break;
    }

    let fragmentsHtml = '';
    if (item.retrieved_fragments && item.retrieved_fragments.length > 0) {
        item.retrieved_fragments.forEach(frag => {
            const source = frag.source ? frag.source.split('|')[0].trim() : '未知来源';
            // 兼容 score 可能是数字或字符串
            let scoreDisplay = frag.score;
            if (typeof frag.raw_score === 'number') {
                scoreDisplay = (frag.raw_score * 100).toFixed(1) + '%';
            }

            fragmentsHtml += `
                <div style="background:#fff; border:1px solid #eee; padding:8px; margin-top:5px; border-radius:4px; font-size:12px; color:#666;">
                    <div style="color:#1890ff; font-weight:bold; margin-bottom:2px;">
                        📄 ${source} <span style="font-weight:normal; color:#999;">(匹配度: ${scoreDisplay})</span>
                    </div>
                    <div style="line-height:1.4;">${frag.content}</div>
                </div>
            `;
        });
    } else {
        fragmentsHtml = '<div style="padding:5px; color:#999; font-style:italic;">未找到相关知识库片段</div>';
    }

    const html = `
        <div class="result-item-card" style="border:1px solid ${styleConfig.borderColor}; border-radius:6px; margin-bottom:15px; overflow:hidden; box-shadow:0 1px 2px rgba(0,0,0,0.03); opacity: 0; animation: fadeIn 0.5s forwards;">
            <div style="background:${styleConfig.bgColor}; padding:8px 12px; border-bottom:1px solid ${styleConfig.borderColor}; display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:bold; color:#333;">片段 ${index + 1}</span>
                <span style="font-weight:bold; font-size:12px; color:${styleConfig.color};">${styleConfig.icon}</span>
            </div>

            <div style="padding:12px;">
                <div style="margin-bottom:10px;">
                    <div style="font-size:12px; color:#999; margin-bottom:4px;">待审核文本:</div>
                    <div style="background:#fafafa; padding:8px; border-radius:4px; color:#333; line-height:1.5;">${item.segment_content}</div>
                </div>

                ${status !== 'fully_consistent' ? `
                    <div style="margin-bottom:12px;">
                        <div style="font-size:12px; color:${styleConfig.color}; margin-bottom:4px;">🔴 分析与建议:</div>
                        <div style="margin-bottom:5px; color:#333;">${comp.diff_description || '无详细描述'}</div>
                        <div style="background:#fffbe6; border:1px solid #ffe58f; color:#d46b08; padding:8px; border-radius:4px; font-size:12px;">
                            <strong>💡 建议修改：</strong> ${comp.suggestion || '无'}
                        </div>
                    </div>
                ` : ''}

                <div>
                    <div onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'"
                         style="cursor:pointer; color:#1890ff; font-size:12px; user-select:none;">
                         📚 查看检索依据 (${item.retrieved_fragments.length}) ▼
                    </div>
                    <div style="display:none; margin-top:5px;">${fragmentsHtml}</div>
                </div>
            </div>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', html);
}

// 补充一个简单的淡入动画到页面style里，或者common.css
// 动态添加 style
const style = document.createElement('style');
style.innerHTML = `
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
`;
document.head.appendChild(style);