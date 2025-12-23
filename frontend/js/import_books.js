/**
 * import_books.js - 书本管理与任务执行 (UI 统一版)
 */

window.initImportBooks = function() {
    loadBookList();
}

window.loadBookList = async function() {
    const tbody = document.getElementById('book-list-body');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="8" class="loading-text">加载中...</td></tr>';

    try {
        // 调用我们刚刚统一的无参接口
        const res = await fetch('/api/import/book/list', {
            method: 'POST'
        });
        const json = await res.json();

        tbody.innerHTML = '';
        if (json.status !== 'success' || !json.data || json.data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="loading-text">暂无任务，请添加新书</td></tr>';
            return;
        }

        json.data.forEach(item => {
            const tr = document.createElement('tr');

            // 防止除以零
            const splitPct = (item.total_segments > 0) ? (item.processed_segments / item.total_segments * 100).toFixed(0) : 0;
            const embedPct = (item.total_fragments > 0) ? (item.imported_fragments / item.total_fragments * 100).toFixed(0) : 0;

            let statusHtml = `<span class="badge badge-ready">${item.status || 'ready'}</span>`;
            if (item.status === 'processing') statusHtml = `<span class="badge badge-processing">进行中</span>`;
            if (item.status === 'completed') statusHtml = `<span class="badge badge-completed">已完成</span>`;

            // 安全处理 JSON 字符串用于 onclick
            const itemJson = JSON.stringify(item).replace(/'/g, "&#39;").replace(/"/g, "&quot;");

            tr.innerHTML = `
                <td>${item.book_id}</td>
                <td title="${item.book_name}"><div class="cell-text-truncate" style="font-weight:600;">${item.book_name}</div></td>
                <td title="${item.file_path}"><div class="cell-text-truncate" style="color:#888;">${item.file_path}</div></td>

                <td>
                    <div style="font-size:11px; display:flex; justify-content:space-between;">
                        <span>${item.processed_segments || 0}/${item.total_segments || 0}</span>
                        <span>${splitPct}%</span>
                    </div>
                    <div class="progress-bar-bg"><div class="progress-bar-fill fill-blue" style="width:${splitPct}%"></div></div>
                </td>

                <td>
                    <div style="font-size:11px; display:flex; justify-content:space-between;">
                        <span>${item.imported_fragments || 0}/${item.total_fragments || 0}</span>
                        <span>${embedPct}%</span>
                    </div>
                    <div class="progress-bar-bg"><div class="progress-bar-fill fill-green" style="width:${embedPct}%"></div></div>
                </td>

                <td><span style="font-size:12px; color:#666;">${item.target_collection}</span></td>
                <td>${statusHtml}</td>

                <td>
                    <div class="action-text-group">
                        <span class="btn-link" onclick="window.runTask('split', ${item.book_id})">切分</span>
                        <span class="sep">|</span>
                        <span class="btn-link" onclick="window.runTask('process', ${item.book_id})">处理</span>
                        <span class="sep">|</span>
                        <span class="btn-link" onclick="window.runTask('embed', ${item.book_id})">入库</span>
                        <span class="sep" style="margin:0 10px; border-left:1px solid #ddd; height:12px;"></span>
                        <span class="btn-link" style="color:#666" onclick='window.openBookModal(${itemJson})'>编辑</span>
                        <span class="sep">|</span>
                        <span class="btn-link delete" onclick="window.deleteBook(${item.book_id})">删除</span>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });

    } catch (e) {
        console.error(e);
        tbody.innerHTML = `<tr><td colspan="8" class="error-text">加载失败: ${e.message}</td></tr>`;
    }
}

// 2. 执行任务 (流式)
window.runTask = async function(step, id) {
    const logBox = document.getElementById('import-log-box');
    const stepName = { 'split': '机械切分', 'process': 'AI结构化', 'embed': '向量入库' }[step];

    // 插入一条开始日志
    const startDiv = document.createElement('div');
    startDiv.className = 'log-line info';
    startDiv.style.borderTop = "1px solid #bae7ff"; // 醒目分隔线
    startDiv.style.marginTop = "10px";
    startDiv.style.paddingTop = "10px";
    startDiv.innerText = `> [${new Date().toLocaleTimeString()}] 启动任务: [${stepName}] (BookID: ${id})...`;
    logBox.appendChild(startDiv);
    logBox.scrollTop = logBox.scrollHeight;

    try {
        const res = await fetch(`/api/import/task/run?step=${step}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ book_id: id, ai_type: 'none' })
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const text = decoder.decode(value, { stream: true });
            const lines = text.split('\n');

            for (const line of lines) {
                if (!line.trim()) continue;

                if (line.startsWith('LOG: ')) {
                    const msg = line.substring(5);
                    const div = document.createElement('div');
                    div.className = 'log-line';
                    div.innerText = `  ${msg}`;
                    logBox.appendChild(div);
                    logBox.scrollTop = logBox.scrollHeight;
                } else if (line.startsWith('DATA: ')) {
                    const data = JSON.parse(line.substring(6));
                    const div = document.createElement('div');
                    if (data.status === 'success') {
                        div.className = 'log-line success';
                        div.innerText = `> ✅ 任务完成！`;
                    } else {
                        div.className = 'log-line error';
                        div.innerText = `> ❌ 任务出错: ${data.msg}`;
                    }
                    logBox.appendChild(div);
                    logBox.scrollTop = logBox.scrollHeight;
                    window.loadBookList(); // 刷新进度
                }
            }
        }
    } catch (e) {
        const div = document.createElement('div');
        div.className = 'log-line error';
        div.innerText = `> ❌ 请求异常: ${e}`;
        logBox.appendChild(div);
    }
}

// ... (openBookModal, saveBook, deleteBook 保持不变) ...
window.openBookModal = function(data=null) {
    document.getElementById('book-modal').classList.remove('hidden');
    if(data) {
        document.getElementById('book-id').value = data.book_id;
        document.getElementById('book-name').value = data.book_name;
        document.getElementById('book-path').value = data.file_path;
        document.getElementById('book-collection').value = data.target_collection;
        document.getElementById('book-batch').value = data.batch_size;
    } else {
        document.getElementById('book-id').value = "";
        document.getElementById('book-name').value = "";
        document.getElementById('book-path').value = "";
        document.getElementById('book-collection').value = "Pharmacopoeia";
        document.getElementById('book-batch').value = "5";
    }
}
window.closeBookModal = function() { document.getElementById('book-modal').classList.add('hidden'); }
window.saveBook = async function() {
    const id = document.getElementById('book-id').value;
    const name = document.getElementById('book-name').value;
    const path = document.getElementById('book-path').value;
    const col = document.getElementById('book-collection').value;
    const batch = document.getElementById('book-batch').value;
    if(!name || !path) { alert("书名和路径必填"); return; }
    try {
        await fetch('/api/import/book/save', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({book_id: id?parseInt(id):null, book_name: name, file_path: path, target_collection: col, batch_size: parseInt(batch)})
        });
        window.closeBookModal(); window.loadBookList();
    } catch(e){alert(e);}
}
window.deleteBook = async function(id) {
    if(!confirm("确定删除？")) return;
    await fetch('/api/import/book/delete', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({book_id:id})});
    window.loadBookList();
}

// 挂载
window.initImportBooks = initImportBooks;
window.loadBookList = loadBookList;
window.runTask = runTask;
window.openBookModal = openBookModal;
window.closeBookModal = closeBookModal;
window.saveBook = saveBook;
window.deleteBook = deleteBook;