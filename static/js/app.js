/**
 * Global App Logic
 */
async function globalRefresh() {
    try {
        const response = await fetch('/api/v1/control/status');
        const status = await response.json();
        
        // Update top-level meta if exists
        const pendingEl = document.getElementById('meta-pending');
        if (pendingEl) pendingEl.textContent = status.active_learning?.queued || 0;
        
        const processedEl = document.getElementById('meta-processed');
        if (processedEl) processedEl.textContent = status.job_counts?.succeeded || 0;

        const navBadgeReview = document.getElementById('nav-badge-review');
        if (navBadgeReview) navBadgeReview.textContent = status.active_learning?.queued || 0;

        // Page specific callbacks
        if (window.onStatusUpdate) {
            window.onStatusUpdate(status);
        }
    } catch (e) {
        console.error("Global refresh failed", e);
    }
}

// Poll every 10 seconds (increased from 5 for performance)
setInterval(globalRefresh, 10000);

// Only run on load if not on a data-heavy page (like Settings or Review)
// 仅在非重数据页面（如设置或审核）上启动加载时运行
window.addEventListener('load', () => {
    // If the current page doesn't have its own refreshSettings, run global one
    if (typeof window.refreshSettings !== 'function') {
        globalRefresh();
    }
});
