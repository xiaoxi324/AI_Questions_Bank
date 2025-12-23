/**
 * config.js - 系统配置模块
 */

window.initConfig = function() {
    loadSearchCollections();
}

// 加载集合列表 (包含详细概览) 和当前配置
async function loadSearchCollections() {
    const container = document.getElementById('collection-list');
    const loading = document.getElementById('collection-loading');

    try {
        // 1. 并行请求
        const [resOverview, resConf] = await Promise.all([
            fetch('/api/knowledge/overview').then(r => r.json()),
            fetch('/api/config/get?key=search_collections').then(r => r.json())
        ]);

        if (loading) loading.style.display = 'none';

        const dbData = resOverview.data || [];

        // --- 核心修复逻辑开始 ---
        let rawConfig = resConf.data;
        let activeCollections = [];

        console.log("🛠️ [调试] 后端返回的配置原始数据:", rawConfig);

        if (rawConfig) {
            // 情况 A: 已经是数组
            if (Array.isArray(rawConfig)) {
                activeCollections = rawConfig;
            }
            // 情况 B: 是字符串 (例如数据库存的是JSON字符串)，尝试解析
            else if (typeof rawConfig === 'string') {
                try {
                    // 尝试把 "['A','B']" 解析为数组
                    // 注意：如果存储格式是单引号python风格，JSON.parse会报错，这里做个简单兼容
                    let fixedString = rawConfig.replace(/'/g, '"');
                    activeCollections = JSON.parse(fixedString);
                } catch (e) {
                    console.warn("⚠️ 配置解析失败，将作为普通字符串处理", e);
                    // 这种情况下，可能只是个普通字符串
                    activeCollections = [rawConfig];
                }
            }
        } else {
            console.log("⚠️ 未读取到配置，将不默认勾选任何旧集合");
        }

        console.log("✅ [调试] 最终生效的选中列表:", activeCollections);
        // --- 核心修复逻辑结束 ---

        if (dbData.length === 0) {
            container.innerHTML = `<div style="padding:20px; text-align:center;">暂无数据</div>`;
            return;
        }

        // 2. 渲染 HTML
        let html = '';

        dbData.forEach(item => {
            const colName = item.collection_name;

            // 判断是否选中：确保精确匹配
            const isChecked = activeCollections.includes(colName) ? 'checked' : '';
            const totalCount = item.total_count || 0;

            let sourcesHtml = '';
            if (item.sources && item.sources.length > 0) {
                sourcesHtml = item.sources.map(src => `
                    <div class="source-item">
                        <i>📖</i>
                        <span title="${src.name}">${src.name}</span>
                        <span class="source-count">${src.count}</span>
                    </div>
                `).join('');
            } else {
                sourcesHtml = '<span style="color:#ccc; font-size:12px;">(无来源信息)</span>';
            }

            html += `
                <div class="collection-item">
                    <div class="collection-header-row">
                        <label>
                            <input type="checkbox" class="col-checkbox" value="${colName}" ${isChecked}>
                            <span class="collection-name">${colName}</span>
                            <span class="total-badge">共 ${totalCount} 条</span>
                        </label>
                    </div>
                    <div class="source-list">
                        ${sourcesHtml}
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;

    } catch (e) {
        console.error(e);
        if (loading) loading.innerText = "数据加载异常";
    }
}

// 保存配置
window.saveSearchConfig = async function() {
    const checkboxes = document.querySelectorAll('.col-checkbox:checked');
    const selected = Array.from(checkboxes).map(cb => cb.value);

    // 允许不选（有时候确实想关闭检索），但给出提示
    if (selected.length === 0) {
        if(!confirm("⚠️ 您没有勾选任何知识库。\n这会导致“定春”审题时无法查阅任何书本依据。\n确定要保存吗？")) {
            return;
        }
    }

    const btn = document.querySelector('.config-footer .btn');
    const oldText = btn.innerText;
    btn.innerText = "保存中...";
    btn.disabled = true;

    try {
        const res = await fetch('/api/config/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                config_key: 'search_collections',
                value: selected
            })
        });
        const data = await res.json();

        if (data.status === 'success') {
            alert("✅ 配置已更新！");
        } else {
            alert("❌ 保存失败: " + (data.msg || "未知错误"));
        }
    } catch (e) {
        alert("网络错误: " + e);
    } finally {
        btn.innerText = oldText;
        btn.disabled = false;
    }
}

window.initConfig = initConfig;
window.saveSearchConfig = saveSearchConfig;