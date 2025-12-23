/**
 * core.js - 核心基础设施
 * 包含：全局变量、路由逻辑、通用工具函数
 */

// ================= 全局变量 (所有模块通用) =================
window.currentPage = 1;
window.pageSize = 50;
window.currentQId = null;
window.currentHistoryCache = {};

// 知识库模块变量
window.currentKbPage = 1;
window.currentKbPageSize = 20;
window.metaKeys = [];

// ================= 1. 路由逻辑 =================

// 页面加载完成后，默认进入题库页
document.addEventListener('DOMContentLoaded', () => {
    window.loadPage('library');
});

/**
 * 动态加载页面片段
 */
window.loadPage = async function(pageName) {
    const container = document.getElementById('app-container');

    // 1. 菜单高亮切换
    document.querySelectorAll('.menu-item').forEach(el => {
        el.classList.remove('active');
        if(el.dataset.page === pageName) el.classList.add('active');
    });

    // 2. 显示 Loading
    container.innerHTML = '<div class="loading-placeholder">正在加载模块...</div>';

    try {
        // 3. 请求 HTML
        const res = await fetch(`/pages/${pageName}.html`);
        if (!res.ok) throw new Error(`页面加载失败: ${res.status}`);
        const html = await res.text();
        container.innerHTML = html;

        // 4. 触发各模块的初始化函数
        // -------------------------------------------------
        if (pageName === 'library' && window.initLibrary) window.initLibrary();
        if (pageName === 'add' && window.initAdd) window.initAdd();
        if (pageName === 'tool' && window.initTool) window.initTool();
        if (pageName === 'knowledge' && window.initKnowledge) window.initKnowledge();
        if (pageName === 'import_books' && window.initImportBooks) window.initImportBooks();
        if (pageName === 'audit' && window.initAudit) window.initAudit();
        if (pageName === 'config' && window.initConfig) window.initConfig();
        if (pageName === 'messages' && window.initMessages) window.initMessages();
        if (pageName === 'batch_review' && window.initBatchReview) window.initBatchReview();
        if (pageName === 'AI_search' && window.initAISearch) window.initAISearch();

        // 修正点：使用完整的函数调用和块结构
        if (pageName === 'make_question' && window.initQuestionGen) {
            window.initQuestionGen();
        }
        // -------------------------------------------------

    } catch (e) {
        console.error(e);
        container.innerHTML = `<div class="error-state">加载失败: ${e.message}</div>`;
    }
}

// ================= 2. 通用工具函数 =================

/**
 * 获取状态对应的 CSS 类名 (红绿灯)
 */
window.getStatusClass = function(statusText) {
    if (!statusText) return 'wait';
    if (statusText.includes('通过') || statusText.includes('正确')) return 'pass';
    if (statusText.includes('驳回') || statusText.includes('错误')) return 'fail';
    if (statusText === '未执行') return 'wait';
    return 'warn';
}

/**
 * HTML 转义 (防止 XSS)
 */
window.escapeHtml = function(text) {
    if (!text) return "";
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}