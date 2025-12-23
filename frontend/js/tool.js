/**
 * tool.js - 药典查询与修改模块 (升级版：支持级标过滤)
 */

function initTool() {
    // 默认聚焦在内容框，因为很多时候用户只想快搜
    const input = document.getElementById('tool-query');
    if(input) input.focus();
}

async function runToolSearch() {
    const inputQuery = document.getElementById('tool-query');
    const inputFilter = document.getElementById('tool-filter');
    const resultArea = document.getElementById('tool-results');

    const queryText = inputQuery.value.trim();
    const filterText = inputFilter.value.trim();

    // 如果内容和过滤都为空，不执行
    if(!queryText && !filterText) return;

    // 根据是否有过滤词，决定提示语
    const loadingMsg = filterText
        ? `正在进行级标定向检索 [${filterText}] ...`
        : '正在极速检索...';

    resultArea.innerHTML = `<div class="loading-text">${loadingMsg}</div>`;

    try {
        let apiUrl = '';
        let payload = {};

        // === 核心分支逻辑 ===
        if (filterText) {
            // 模式 A: 有过滤词 -> 走新接口
            apiUrl = '/api/tool/level_lookup';
            payload = {
                title_filter: filterText,
                search_content: queryText || " " // 如果只写了过滤词没写内容，传空格防止报错
            };
        } else {
            // 模式 B: 无过滤词 -> 走旧接口 (保持极速)
            apiUrl = '/api/tool/search';
            payload = {
                keyword: queryText
            };
        }

        const res = await fetch(apiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        // 两个接口返回的数据都在 data.data 里，但在字段命名上略有不同
        // 下面的渲染逻辑做了兼容处理
        if(data.status === 'success' && data.data && data.data.length > 0) {
            let html = '';

            // 如果是新接口，可能返回了 total_candidates_scanned，可以展示一下
            if (data.total_candidates_scanned !== undefined) {
                 html += `<div style="padding: 0 10px; color: #666; font-size: 0.9em; margin-bottom: 10px;">
                            🎯 扫描候选: ${data.total_candidates_scanned} 条 | 命中: ${data.data.length} 条
                          </div>`;
            }

            data.data.forEach((item, index) => {
                const cardId = `rag-card-${index}`;

                // === 字段兼容适配 ===
                // 旧接口直接返回 score (字符串百分比), item.source, item.path
                // 新接口返回 score_percent, item.metadata['组合标题'], item.metadata['完整路径']

                let displayScore = item.score_percent || item.score || 'N/A';

                let displayPath = item.path;
                if (!displayPath && item.metadata) {
                    displayPath = item.metadata['完整路径'] || '路径未知';
                }

                let displaySource = item.source;
                if (!displaySource && item.metadata) {
                    // 手动拼接来源显示
                    const srcFile = item.metadata['来源文件'] || 'Base';
                    const title = item.metadata['组合标题'] || '无标题';
                    displaySource = `${srcFile} | ${title}`;
                }

                html += `
                    <div class="rag-card" id="${cardId}" data-real-id="${item.id}">
                        <div class="rag-header">
                            <div class="rag-info">
                                <div>
                                    <span class="rag-score">${displayScore}</span>
                                    <span style="font-weight:600">${escapeHtml(displaySource)}</span>
                                </div>
                                <div class="rag-path">${escapeHtml(displayPath)}</div>
                            </div>
                            <div class="rag-actions">
                                <button class="btn btn-xs btn-default" onclick="toggleEditMode('${cardId}')">✏️ 编辑</button>
                            </div>
                        </div>
                        <div class="rag-body display-mode">${escapeHtml(item.content).replace(/\n/g, '<br>')}</div>
                        <div class="rag-body edit-mode hidden">
                            <textarea class="rag-edit-textarea">${item.content}</textarea>
                            <div style="text-align:right; margin-top:10px;">
                                <button class="btn btn-xs" onclick="cancelEdit('${cardId}')">取消</button>
                                <button class="btn btn-xs btn-primary" onclick="saveEdit('${cardId}')">💾 确认修改</button>
                            </div>
                        </div>
                    </div>
                `;
            });
            resultArea.innerHTML = html;
        } else {
            resultArea.innerHTML = '<div class="empty-state">未找到相关内容</div>';
        }
    } catch(e) {
        resultArea.innerHTML = `<div class="error-state">❌ 检索出错: ${e.message}</div>`;
    }
}

// 修改 fillSearch 支持两个参数
function fillSearch(filterVal, queryVal) {
    const inputQuery = document.getElementById('tool-query');
    const inputFilter = document.getElementById('tool-filter');

    if(inputFilter) inputFilter.value = filterVal || '';
    if(inputQuery) inputQuery.value = queryVal || filterVal; // 兼容旧逻辑

    runToolSearch();
}

function toggleEditMode(cardId) {
    const card = document.getElementById(cardId);
    card.querySelector('.display-mode').classList.add('hidden');
    card.querySelector('.edit-mode').classList.remove('hidden');
    card.querySelector('.rag-actions button').style.display = 'none';
}

function cancelEdit(cardId) {
    const card = document.getElementById(cardId);
    card.querySelector('.display-mode').classList.remove('hidden');
    card.querySelector('.edit-mode').classList.add('hidden');
    card.querySelector('.rag-actions button').style.display = 'inline-block';
}

async function saveEdit(cardId) {
    const card = document.getElementById(cardId);
    const realId = card.dataset.realId;
    const newContent = card.querySelector('textarea').value;

    if(!newContent.trim()) { alert("内容不能为空"); return; }

    // UI Loading
    const btn = card.querySelector('.btn-primary');
    const oldText = btn.innerText;
    btn.innerText = "保存中...";
    btn.disabled = true;

    try {
        const res = await fetch('/api/tool/update_rag', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: realId, content: newContent })
        });
        const data = await res.json();

        if(data.status === 'success') {
            card.querySelector('.display-mode').innerHTML = escapeHtml(newContent).replace(/\n/g, '<br>');
            cancelEdit(cardId);
            alert("✅ 知识库已更新！");
        } else {
            alert("❌ 保存失败: " + data.msg);
        }
    } catch(e) { alert("网络错误: " + e); }
    finally {
        btn.innerText = oldText;
        btn.disabled = false;
    }
}

// 简单的 HTML 转义工具，防止 XSS
function escapeHtml(text) {
    if (!text) return text;
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}