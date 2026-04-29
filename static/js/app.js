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

// Poll every 5 seconds
setInterval(globalRefresh, 5000);
window.addEventListener('load', globalRefresh);
