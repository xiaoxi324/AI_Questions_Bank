/**
 * knowledge.js - 最终修正版
 * 逻辑：前端只负责收集 L1-L8 和纯内容，后端负责拼接向量文本
 */

let currentKbPage = 1;
let currentKbPageSize = 20;

const FIXED_META_KEYS = [
    "来源文件", "组合标题", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8"
];

// 1. 初始化
window.initKnowledge = function() {
    window.loadCollections();
}

// 2. 加载集合
window.loadCollections = async function() {
    try {
        const res = await fetch('/api/knowledge/collections');
        const data = await res.json();
        const select = document.getElementById('collection-select');
        if (!select) return;
        select.innerHTML = '';
        if (data.data && data.data.length > 0) {
            data.data.forEach(col => {
                const opt = document.createElement('option');
                opt.value = col;
                opt.innerText = col;
                if (col === 'Pharmacopoeia_Official') opt.selected = true;
                select.appendChild(opt);
            });
        } else {
            select.innerHTML = '<option value="">无集合</option>';
        }
        window.loadMetadataConfig();
    } catch(e) { console.error(e); }
}

// 3. 加载筛选栏
window.loadMetadataConfig = async function() {
    const filterDiv = document.getElementById('filter-container');
    let html = '';
    FIXED_META_KEYS.forEach(key => {
        let label = key;
        if (key.startsWith('L')) label = `${key} 层级`;
        html += `
            <div class="filter-item">
                <span class="filter-label">${label}</span>
                <input type="text" class="filter-input" data-key="${key}"
                       placeholder="搜索..." onkeypress="if(event.key==='Enter') loadKnowledgeList(1)">
            </div>`;
    });
    filterDiv.innerHTML = html;
    window.loadKnowledgeList(1);
}

// 4. 加载列表
window.loadKnowledgeList = async function(page) {
    window.currentKbPage = page;
    const colName = document.getElementById('collection-select').value;
    const tbody = document.getElementById('knowledge-list-body');
    if (!colName) return;

    // 收集筛选
    const filters = {};
    document.querySelectorAll('.filter-input').forEach(input => {
        if(input.value.trim()) filters[input.dataset.key] = input.value.trim();
    });

    tbody.innerHTML = '<tr><td colspan="3" class="loading-text">检索中...</td></tr>';

    try {
        const res = await fetch('/api/knowledge/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                collection_name: colName,
                page: window.currentKbPage,
                page_size: window.currentKbPageSize,
                filters: filters
            })
        });
        const data = await res.json();
        tbody.innerHTML = '';
        if(!data.data || data.data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="loading-text">暂无数据</td></tr>';
            return;
        }

        // 渲染每一行
        data.data.forEach(item => {
            const m = item.metadata || {};
            const tr = document.createElement('tr');

            // --- A. 数据处理 ---
            const allLevels = [m.L1, m.L2, m.L3, m.L4, m.L5, m.L6, m.L7, m.L8].filter(v => v && v.trim() !== '');
            const topRow = [m.L1, m.L2].filter(v => v).join(' <span style="color:#ddd; margin:0 3px;">/</span> ') || '<span style="color:#ccc">未分类</span>';

            let bottomRowText = m['组合标题'];
            if (!bottomRowText) {
                bottomRowText = allLevels.slice(-3).reverse().join(' / ');
            }
            if (!bottomRowText) bottomRowText = '-';

            // 【关键修改】列表展示纯内容
            // 如果 metadata 里有 "片段内容" (纯内容)，就显示它；
            // 否则才显示 content (可能是拼接了标题的文本，作为兜底)
            const displayContent = m['片段内容'] ? m['片段内容'] : item.content;

            // --- B. DOM 构造 ---
            tr.innerHTML = `
                <td style="vertical-align: top; padding: 10px 8px; border-bottom: 1px solid #f0f0f0;">
                    <div style="font-weight: 600; color: #333; font-size: 14px; margin-bottom: 4px;">
                        ${topRow}
                    </div>
                    <div style="font-size: 12px; color: #888; line-height: 1.4;">
                        <span style="color:#aaa;">↳</span> ${bottomRowText}
                    </div>
                    ${ m['来源文件'] ? `<div style="font-size:10px; color:#aaa; margin-top:3px;">📄 ${window.escapeHtml(m['来源文件'])}</div>` : '' }
                </td>

                <td class="kb-col-content" style="vertical-align: top; padding: 10px 8px; border-bottom: 1px solid #f0f0f0;">
                    <div class="content-cell-clamp" title="${window.escapeHtml(displayContent)}">
                        ${window.escapeHtml(displayContent)}
                    </div>
                </td>

                <td class="kb-col-action" style="vertical-align: top; padding: 10px 8px; border-bottom: 1px solid #f0f0f0;">
                    <span class="btn-link" onclick='window.openKnowledgeModal(${JSON.stringify(item).replace(/'/g, "&#39;")})'>编辑</span>
                    <span class="btn-link delete" style="color:red;" onclick="window.deleteDoc('${item.id}')">删除</span>
                </td>
            `;
            tbody.appendChild(tr);
        });
        document.getElementById('kb-page-info').innerText = `第 ${data.page} 页`;
    } catch(e) {
        tbody.innerHTML = `<tr><td colspan="3" class="error-text">加载错误: ${e.message}</td></tr>`;
    }
}

// 5. 翻页
window.changeKbPage = function(delta) {
    const newPage = window.currentKbPage + delta;
    if(newPage < 1) return;
    window.loadKnowledgeList(newPage);
}

// 6. 重置
window.resetFilters = function() {
    document.querySelectorAll('.filter-input').forEach(i => i.value = '');
    window.loadKnowledgeList(1);
}

// 7. 打开弹窗 (【关键修改】：优先回显纯内容)
window.openKnowledgeModal = function(data = null) {
    const modal = document.getElementById('knowledge-modal');
    const title = document.getElementById('kb-modal-title');
    modal.classList.remove('hidden');

    if (data) {
        title.innerText = "修改片段 (属性只读)";
        document.getElementById('kb-id').value = data.id;

        const m = data.metadata || {};

        // 【核心修正】防止回显 "标题：内容" 这种重复数据
        // 如果 metadata 里存了纯净的 "片段内容"，就用它；否则用 content 兜底
        const rawContent = (m['片段内容']) ? m['片段内容'] : data.content;
        document.getElementById('kb-content').value = rawContent;

        // 填充 L1-L8
        for(let i=1; i<=8; i++) {
            const el = document.getElementById(`kb-L${i}`);
            let val = m[`L${i}`] || '';
            if(!val && i===1) val = m['章名'] || ''; // 兼容旧数据
            if(!val && i===2) val = m['节名'] || '';
            if(el) el.value = val;
        }

        document.getElementById('kb-combo-title').value = m['组合标题'] || '将在保存时重新计算';
        document.getElementById('kb-source').value = m['来源文件'] || '未知来源';

    } else {
        title.innerText = "新增片段";
        document.getElementById('kb-id').value = "";
        document.getElementById('kb-content').value = "";
        for(let i=1; i<=8; i++) {
             const el = document.getElementById(`kb-L${i}`);
             if(el) el.value = '';
        }
        document.getElementById('kb-combo-title').value = "自动生成...";
        document.getElementById('kb-source').value = "Manual_Entry";
    }
}

// 8. 关闭弹窗
window.closeKbModal = function() {
    document.getElementById('knowledge-modal').classList.add('hidden');
}

// 9. 保存 (【关键修改】：移除前端向量文本计算)
window.saveKnowledge = async function() {
    const colName = document.getElementById('collection-select').value;
    const docId = document.getElementById('kb-id').value;
    const content = document.getElementById('kb-content').value;

    if(!content) { alert("内容不能为空"); return; }

    const levels = [];
    const metadataRaw = {};

    metadataRaw["来源文件"] = document.getElementById('kb-source').value;

    for(let i=1; i<=8; i++) {
        const val = document.getElementById(`kb-L${i}`).value.trim();
        if(val) {
            levels.push(val);
            metadataRaw[`L${i}`] = val;
        }
    }

    // 自动计算组合标题 (用于 metadata 显示)
    let comboTitle = "未分类";
    if (levels.length > 0) {
        comboTitle = levels.slice(-3).reverse().join(' / ');
    }
    metadataRaw["组合标题"] = comboTitle;

    // 【删除】这里不再计算 vectorText = "路径+内容"
    // 我们相信后端会处理拼接逻辑

    console.log("Saving...", { comboTitle, content });

    try {
        const res = await fetch('/api/knowledge/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                collection_name: colName,
                doc_id: docId || null,
                content: content,      // 发送纯内容
                metadata_raw: metadataRaw, // 发送元数据
                // vector_content_calculated: null // 不发这个了，后端自己拼
            })
        });
        const result = await res.json();

        if(result.status === 'success') {
            alert(`保存成功！\n标题：${comboTitle}`);
            window.closeKbModal();
            window.loadKnowledgeList(window.currentKbPage);
        } else {
            alert("失败: " + result.msg);
        }
    } catch(e) { alert("网络错误: " + e); }
}

// 10. 删除
window.deleteDoc = async function(id) {
    if(!confirm("确定删除？")) return;
    const colName = document.getElementById('collection-select').value;
    try {
        const res = await fetch('/api/knowledge/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ collection_name: colName, doc_id: id })
        });
        window.loadKnowledgeList(window.currentKbPage);
    } catch(e) { alert("删除失败: " + e); }
}

window.escapeHtml = function(text) {
    if (!text) return '';
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

// 挂载
window.initKnowledge = initKnowledge;
window.loadCollections = loadCollections;
window.loadMetadataConfig = loadMetadataConfig;
window.loadKnowledgeList = loadKnowledgeList;
window.changeKbPage = changeKbPage;
window.resetFilters = resetFilters;
window.openKnowledgeModal = openKnowledgeModal;
window.closeKbModal = closeKbModal;
window.saveKnowledge = saveKnowledge;
window.deleteDoc = deleteDoc;