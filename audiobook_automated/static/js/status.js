// File: audiobook_automated/static/js/status.js
/**
 * Polling logic for the status page.
 * Fetches JSON status updates and refreshes the table DOM to avoid full page reloads.
 */

// Explicitly expose functions and state to the global scope for testing
window.updateTable = updateTable;
window.escapeHtml = escapeHtml;
window.statusInterval = null; // Exposed for testing cleanup

document.addEventListener("DOMContentLoaded", () => {
    const tableBody = document.getElementById("status-table-body");
    // Only run if we are on the status page and the table is present
    if (!tableBody) return;

    // Poll every 5 seconds
    const pollStatus = async () => {
        try {
            const response = await fetch("/status?json=1");
            if (!response.ok) {
                console.error("Status poll failed:", response.status);
                return;
            }
            const data = await response.json();
            if (Array.isArray(data)) {
                updateTable(tableBody, data);
            }
        } catch (error) {
            console.error("Failed to fetch status:", error);
        } finally {
            window.statusInterval = setTimeout(pollStatus, 5000);
        }
    };

    pollStatus();
});

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
                <td colspan="5" class="empty-message">No active downloads found in category.</td>
            </tr>`;
        return;
    }

    // Build HTML string for rows
    // SECURITY: Ensure ALL dynamic fields are escaped to prevent XSS.
    const rowsHtml = torrents
        .map(
            (torrent) => `
        <tr>
            <td class="cell-title">${escapeHtml(torrent.name)}</td>
            <td class="cell-progress">${torrent.progress}%</td>
            <td class="cell-state">${escapeHtml(torrent.state)}</td>
            <td class="cell-size">${escapeHtml(torrent.size)}</td>
            <td class="cell-action">
                <button class="remove-button remove-torrent-btn" data-torrent-id="${escapeHtml(String(torrent.id))}">Remove</button>
            </td>
        </tr>
    `
        )
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
