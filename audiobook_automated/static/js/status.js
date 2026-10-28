// File: audiobook_automated/static/js/status.js
/**
 * Polling logic for the status page.
 * Fetches JSON status updates and refreshes the table DOM to avoid full page reloads.
 */

// Explicitly expose functions and state to the global scope for testing
window.updateTable = updateTable;
window.escapeHtml = escapeHtml;
window.getStatusBadgeClass = getStatusBadgeClass;
window.statusInterval = null; // Exposed for testing cleanup

document.addEventListener("DOMContentLoaded", () => {
    const tableBody = document.getElementById("status-table-body");
    // Only run if we are on the status page and the table is present
    if (!tableBody) return;

    const pollIndicator = document.getElementById("status-poll-indicator");
    const countBadge = document.getElementById("status-count-badge");

    // Poll every 5 seconds
    const pollStatus = async () => {
        try {
            if (pollIndicator) pollIndicator.classList.add("polling");
            const response = await fetch("/status?json=1");
            if (!response.ok) {
                console.error("Status poll failed:", response.status);
                return;
            }
            const data = await response.json();
            if (Array.isArray(data)) {
                updateTable(tableBody, data);
                if (countBadge) {
                    countBadge.textContent = `${data.length} Active`;
                }
            }
        } catch (error) {
            console.error("Failed to fetch status:", error);
        } finally {
            if (pollIndicator) {
                setTimeout(() => pollIndicator.classList.remove("polling"), 400);
            }
            window.statusInterval = setTimeout(pollStatus, 5000);
        }
    };

    pollStatus();
});

/**
 * Maps a torrent state string to an appropriate badge CSS class.
 * @param {string} state - The raw state string.
 * @returns {string} CSS class name.
 */
function getStatusBadgeClass(state) {
    const s = String(state || "").toLowerCase();
    if (s.includes("download")) return "badge-downloading";
    if (s.includes("seed") || s.includes("finish") || s.includes("complete")) return "badge-seeding";
    if (s.includes("pause") || s.includes("stop")) return "badge-paused";
    if (s.includes("error") || s.includes("fail")) return "badge-error";
    return "badge-other";
}

/**
 * Updates the table body with new torrent data.
 * @param {HTMLElement} tbody - The table body element.
 * @param {Array<{id: string|number, name: string, progress: number, state: string, size: string}>} torrents - List of torrent objects.
 */
function updateTable(tbody, torrents) {
    // If empty list, show empty message
    if (!torrents || torrents.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="empty-message" style="text-align: center; padding: 40px; color: var(--text-muted)">No active downloads found.</td>
            </tr>`;
        return;
    }

    // Build HTML string for rows
    // SECURITY: Ensure ALL dynamic fields are escaped to prevent XSS.
    const rowsHtml = torrents
        .map((torrent) => {
            const progress = typeof torrent.progress === "number" ? torrent.progress : 0;
            const badgeClass = getStatusBadgeClass(torrent.state);
            const fillCompleteClass = progress >= 100 ? "fill-complete" : "";

            return `
        <tr>
            <td class="cell-title">
                <div class="title-with-icon">
                    <span class="book-media-icon" aria-hidden="true">🎧</span>
                    <div class="title-text-group">
                        <span class="title-text">${escapeHtml(torrent.name)}</span>
                        ${torrent.client ? `<span class="torrent-client-tag">${escapeHtml(torrent.client)}</span>` : ""}
                    </div>
                </div>
            </td>
            <td class="cell-progress">
                <div class="progress-cell-wrap">
                    <div class="progress-bar-container" role="progressbar" aria-valuenow="${progress}" aria-valuemin="0" aria-valuemax="100">
                        <div class="progress-bar-fill ${fillCompleteClass}" style="width: ${progress}%"></div>
                    </div>
                    <span class="progress-percentage">${progress}%</span>
                </div>
            </td>
            <td class="cell-state">
                <span class="status-badge ${badgeClass}">${escapeHtml(torrent.state)}</span>
            </td>
            <td class="cell-size">${escapeHtml(torrent.size)}</td>
            <td class="cell-action">
                <button class="remove-button remove-torrent-btn btn-glass-danger" data-torrent-id="${escapeHtml(String(torrent.id))}" title="Remove download">
                    <svg class="action-btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                    <span>Remove</span>
                </button>
            </td>
        </tr>
    `;
        })
        .join("");

    tbody.innerHTML = rowsHtml;
}

/**
 * Helper to escape HTML to prevent XSS.
 * @param {string} str - Raw string.
 * @returns {string} Safe HTML string.
 */
function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
