/**
 * audit.js - 知识审核模块 (UI优化版)
 */

let auditBatchIdx = 0;
let auditBookId = null;
let auditRangeStr = "";
let auditFragments = [];
let auditRanges = [];
window.auditBookCache = [];

window.initAudit = function() {
    console.log("🔍 [1] 初始化知识审核模块...");
    // 调用重命名后的函数
    auditLoadBooks();
}

// 1. 加载书本 (重命名为 auditLoadBooks)
async function auditLoadBooks() {
    console.log("🚀 [2] 发起请求: /api/import/book/list (Audit模块)");
    const select = document.getElementById('audit-book-select');

    // 双重检查：确保当前真的是审核页面
    if (!select) {
        console.error("❌ 错误：在当前页面找不到 id='audit-book-select'，可能是函数名冲突导致跑错页面逻辑了。");
        return;
    }

    select.innerHTML = '<option value="">加载中...</option>';

    try {
        const res = await fetch('/api/import/book/list', { method: 'POST' });

        console.log("📡 [3] 响应状态:", res.status);
        if (!res.ok) throw new Error(`HTTP Error ${res.status}`);

        const json = await res.json();
        console.log("📚 [4] 数据内容:", json);

        select.innerHTML = '';

        if (json.status === 'success' && json.data && json.data.length > 0) {
            window.auditBookCache = json.data;

            json.data.forEach(book => {
                const opt = document.createElement('option');
                opt.value = book.book_id;
                opt.innerText = book.book_name;
                select.appendChild(opt);
            });

            select.selectedIndex = 0;
            console.log(`✅ [5] 默认选中 ID: ${json.data[0].book_id}`);

            // 调用重命名后的加载批次函数
            auditLoadBatches();

        } else {
            select.innerHTML = '<option value="">暂无书本数据</option>';
            document.getElementById('audit-collection-label').innerText = "--";
        }
    } catch(e) {
        console.error("❌ [ERROR] 加载失败:", e);
        select.innerHTML = '<option value="">接口请求失败</option>';
    }
}

// 2. 加载批次范围 (重命名为 auditLoadBatches)
window.loadBookBatches = function() { auditLoadBatches(); } // 兼容HTML中的旧onclick
async function auditLoadBatches() {
    const select = document.getElementById('audit-book-select');
    if (!select.value) return;

    auditBookId = select.value;
    auditBatchIdx = 0;

    const book = window.auditBookCache.find(b => b.book_id == auditBookId);
    if (book) {
        const label = document.getElementById('audit-collection-label');
        if(label) label.innerText = book.target_collection || "--";
    }

    const rangeSelect = document.getElementById('audit-range-select');
    rangeSelect.innerHTML = '<option>加载中...</option>';
    rangeSelect.disabled = true;

    try {
        const res = await fetch('/api/audit/ranges', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ book_id: parseInt(auditBookId) })
        });
        const data = await res.json();

        if (data.status === 'success') {
            auditRanges = data.data || [];
            auditRenderRangeSelect();
            if(auditRanges.length > 0) {
                auditLoadList(0); // 加载第一批
            } else {
                document.getElementById('audit-list-body').innerHTML = '<tr><td colspan="4" class="loading-text">无数据</td></tr>';
                rangeSelect.innerHTML = '<option>无数据</option>';
            }
        }
    } catch(e) { console.error("获取范围失败", e); }
}

function auditRenderRangeSelect() {
    const select = document.getElementById('audit-range-select');
    select.innerHTML = '';

    if (!auditRanges || auditRanges.length === 0) {
        select.innerHTML = '<option value="">无数据</option>';
        select.disabled = true;
        return;
    }

    select.disabled = false;
    auditRanges.forEach((r, idx) => {
        const opt = document.createElement('option');
        opt.value = idx;
        opt.innerText = r;
        select.appendChild(opt);
    });
}

// HTML 中 onclick="window.jumpToBatch()" 需要保留挂载
window.jumpToBatch = function() {
    const select = document.getElementById('audit-range-select');
    auditLoadList(parseInt(select.value));
}

// 3. 加载列表 (重命名为 auditLoadList)
async function auditLoadList(idx) {
    if (!auditBookId) return;
    const tbody = document.getElementById('audit-list-body');
    tbody.innerHTML = '<tr><td colspan="4" class="loading-text">加载中...</td></tr>';

    try {
        const res = await fetch('/api/audit/list', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ book_id: parseInt(auditBookId), current_range_index: idx })
        });
        const data = await res.json();

        if (data.status === 'success') {
            auditBatchIdx = data.current_batch_idx;
            auditRangeStr = data.current_range;
            auditFragments = data.data;

            const select = document.getElementById('audit-range-select');
            if(select) select.value = auditBatchIdx;

            const info = document.getElementById('audit-batch-info');
            if(info) info.innerText = `批次: ${auditBatchIdx+1} / ${auditRanges.length}`;

            auditRenderTable(data.data);
        } else {
            tbody.innerHTML = `<tr><td colspan="4" class="error-text">${data.msg}</td></tr>`;
        }
    } catch(e) { console.error(e); }
}

// 4. 渲染表格 (核心修改：4列 + 纯文本链接)
function auditRenderTable(list) {
    const tbody = document.getElementById('audit-list-body');
    tbody.innerHTML = '';

    if(!list || list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="loading-text">本批次无数据</td></tr>';
        return;
    }

    list.forEach(item => {
        const tr = document.createElement('tr');

        // Status Icon (Pure icon, centered)
        const isEmbedded = item.is_embedded
            ? `<span style="color:#52c41a; font-size:12px;" title="已入库">已入库</span>`
            : `<span style="color:#faad14; font-size:12px;" title="待入库">待入库</span>`;

        // Safe JSON for onclick
        const safeItem = JSON.stringify(item).replace(/'/g, "&#39;").replace(/"/g, "&quot;");

        tr.innerHTML = `
            <td style="vertical-align:top; padding:10px; border-bottom:1px solid #f0f0f0;">
                <div style="font-weight:600; color:#333; font-size:13px; margin-bottom:4px;">
                    ${item.combo_title || '未分类'}
                </div>
                <div style="font-size:11px; color:#999;">
                    ${item.book_name || ''}
                </div>
            </td>

            <td style="vertical-align:top; padding:10px; border-bottom:1px solid #f0f0f0;">
                <div style="max-height:80px; overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; color:#555; font-size:13px; line-height:1.5;">
                    ${item.content}
                </div>
            </td>

            <td style="vertical-align:middle; text-align:center; border-bottom:1px solid #f0f0f0;">
                ${isEmbedded}
            </td>

            <td style="vertical-align:middle; text-align:center; border-bottom:1px solid #f0f0f0;">
                <span class="btn-link" onclick='window.openAuditModal(${safeItem})'>编辑</span>
                <span style="color:#ddd; margin:0 5px;">|</span>
                <span class="btn-link delete" style="color:#ff4d4f;" onclick="window.deleteAuditFragment(${item.fragment_id})">删除</span>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// 5. 翻页
window.changeBatch = function(delta) {
    const newIdx = auditBatchIdx + delta;
    if (newIdx >= 0 && newIdx < auditRanges.length) {
        auditLoadList(newIdx);
    } else {
        alert("没有更多了");
    }
}

// 6. 批量入库
window.batchEmbed = async function() {
    if (!auditFragments.length) return;
    if (!confirm("确定入库？")) return;

    const ids = auditFragments.map(i => i.fragment_id);
    await fetch('/api/audit/embed_batch', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ fragment_ids: ids })
    });
    alert("入库完成");
    auditLoadList(auditBatchIdx); // 刷新
}

// 7. 弹窗相关
window.openAuditModal = function(data) {
    document.getElementById('audit-modal').classList.remove('hidden');
    if(data) {
        document.getElementById('audit-id').value = data.fragment_id;
        document.getElementById('audit-content').value = data.content;
        for(let i=1; i<=8; i++) {
            const el = document.getElementById(`audit-L${i}`);
            if(el) el.value = data[`L${i}`] || '';
        }
    } else {
        document.getElementById('audit-id').value = '';
        document.getElementById('audit-content').value = '';
    }
}

window.closeAuditModal = function() {
    document.getElementById('audit-modal').classList.add('hidden');
}

window.saveAuditFragment = async function() {
    const id = document.getElementById('audit-id').value;
    const l_data = {};
    for(let i=1; i<=8; i++) {
        const val = document.getElementById(`audit-L${i}`).value.trim();
        l_data[`L${i}`] = val;
    }

    const payload = {
        fragment_id: id ? parseInt(id) : null,
        book_id: parseInt(auditBookId),
        book_name: window.auditBookCache.find(b=>b.book_id==auditBookId).book_name,
        content: document.getElementById('audit-content').value,
        source_segment_range: auditRangeStr,
        ...l_data
    };

    const res = await fetch('/api/audit/save_fragment', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    });
    const json = await res.json();
    if(json.status === 'success') {
        closeAuditModal();
        auditLoadList(auditBatchIdx);
    } else {
        alert("保存失败: " + json.msg);
    }
}

window.deleteAuditFragment = async function(id) {
    if(!confirm("删？")) return;
    await fetch('/api/audit/delete_fragment', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({fragment_id: id})
    });
    auditLoadList(auditBatchIdx);
}

// 挂载
window.initAudit = initAudit;
window.loadBookBatches = loadBookBatches;
window.loadAuditList = loadAuditList;
window.changeBatch = changeBatch;
window.batchEmbed = batchEmbed;
window.openAuditModal = openAuditModal;
window.closeAuditModal = closeAuditModal;
window.saveAuditFragment = saveAuditFragment;
window.deleteAuditFragment = deleteAuditFragment;
// 手动挂载 HTML 中 onclick 调用的旧名字，指向新函数
window.loadBookBatches = auditLoadBatches;