/**
 * add.js - 新增题目模块
 */

// 初始化函数 (页面加载时调用)
function initAdd() {
    const input = document.getElementById('raw-input');
    if(input) input.value = '';

    const logDiv = document.getElementById('add-log-area');
    if(logDiv) logDiv.innerHTML = '<div class="log-item info">等待输入...</div>';
}

// 提交解析逻辑
async function parseAndSubmit() {
    const raw = document.getElementById('raw-input').value.trim();
    const sourceSelect = document.getElementById('source-select');
    const logDiv = document.getElementById('add-log-area');

    if(!raw) {
        alert("请填写内容");
        return;
    }

    // 插入开始日志
    const p = document.createElement('div');
    p.className = 'log-item info';
    p.innerText = `> [${new Date().toLocaleTimeString()}] 正在提交解析...`;
    logDiv.appendChild(p);

    // 锁定按钮
    const btn = document.querySelector('.action-bar .btn-primary');
    const oldText = btn.innerText;
    btn.innerText = "处理中...";
    btn.disabled = true;

    try {
        const source = sourceSelect ? sourceSelect.value : '智能审题';

        const res = await fetch('/api/data/question/manage', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'add',
                payload: {
                    raw_text: raw,
                    source: source
                }
            })
        });
        const data = await res.json();

        const p2 = document.createElement('div');
        if(data.status === 'success') {
            p2.className = 'log-item success';
            const countText = data.count ? ` (共${data.count}题)` : "";
            p2.innerText = `✅ 入库成功！${data.msg}${countText}`;
            document.getElementById('raw-input').value = ''; // 成功后清空
        } else {
            p2.className = 'log-item error';
            p2.innerText = `❌ 失败: ${data.msg}`;
        }
        logDiv.appendChild(p2);
        logDiv.scrollTop = logDiv.scrollHeight; // 滚动到底部

    } catch(e) {
        const pErr = document.createElement('div');
        pErr.className = 'log-item error';
        pErr.innerText = `❌ 网络请求错误: ${e}`;
        logDiv.appendChild(pErr);
        console.error(e);
    } finally {
        // 恢复按钮
        btn.innerText = oldText;
        btn.disabled = false;
    }
}

// ==================== 挂载到全局 ====================
window.initAdd = initAdd;
window.parseAndSubmit = parseAndSubmit;