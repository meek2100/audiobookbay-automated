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
    // Only run if we are on the status page
    if (!tableBody) return;

    // Poll every 5 seconds
    window.statusInterval = setInterval(async () => {
        try {
            const response = await fetch("/status?json=1");
            if (!response.ok) {
                console.error("Status poll failed:", response.status);
                return;
            }
            const torrents = await response.json();
            updateTable(tableBody, torrents);
        } catch (error) {
            console.error("Failed to fetch status:", error);
        }
    }, 5000);
});

/**
 * Updates the table body with new torrent data.
 * @param {HTMLElement} tbody - The table body element.
 * @param {Array} torrents - List of torrent objects.
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
            <td>${escapeHtml(torrent.name)}</td>
            <td>${torrent.progress}%</td>
            <td>${escapeHtml(torrent.state)}</td>
            <td>${escapeHtml(torrent.size)}</td>
            <td>
                <button class="remove-button" onclick="deleteTorrent('${torrent.id}')">Remove</button>
            </td>
        </tr>
    `
        )
        .join("");

    tbody.innerHTML = rowsHtml;
}

/**
 * Simple HTML escaping to prevent XSS in table cells.
 */
function escapeHtml(text) {
    if (!text) return "";
    return text
        .toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
