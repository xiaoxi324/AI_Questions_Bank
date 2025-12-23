/**
 * messages.js - 系统消息模块
 */

window.initMessages = function() {
    loadSystemLogs();
}

window.loadSystemLogs = async function() {
    const tbody = document.getElementById('msg-list-body');
    tbody.innerHTML = '<tr><td colspan="4" class="loading-text">加载中...</td></tr>';

    try {
        const res = await fetch('/api/system/logs');
        const data = await res.json();

        tbody.innerHTML = '';
        if(!data.data || data.data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="loading-text">暂无系统消息</td></tr>';
            return;
        }

        data.data.forEach(item => {
            const tr = document.createElement('tr');

            let typeHtml = `<span style="color:#666">${item.log_type}</span>`;
            if(item.log_type === 'error') typeHtml = `<span class="badge badge-error">错误</span>`;

            tr.innerHTML = `
                <td>${typeHtml}</td>
                <td style="font-weight:bold;">${item.source}</td>
                <td style="color:#ff4d4f; font-family:monospace;">${item.message}</td>
                <td style="color:#999; font-size:12px;">${item.create_time}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch(e) { console.error(e); }
}

window.clearLogs = async function() {
    if(!confirm("确定清空所有消息吗？")) return;
    await fetch('/api/system/logs/clear', { method: 'POST' });
    loadSystemLogs();
}

// 挂载
window.initMessages = initMessages;
window.loadSystemLogs = loadSystemLogs;
window.clearLogs = clearLogs;