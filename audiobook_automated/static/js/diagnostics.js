// File: audiobook_automated/static/js/diagnostics.js
/**
 * Real-time Diagnostics Dashboard Controller
 * Handles auto-refresh, badge updates, logs streaming, and log file download.
 */

document.addEventListener("DOMContentLoaded", () => {
    const refreshBtn = document.getElementById("refresh-diag-btn");
    const refreshLogsBtn = document.getElementById("refresh-logs-btn");
    const inspectBtn = document.getElementById("run-inspect-btn");
    const inspectInput = document.getElementById("inspect-input");
    const inspectOutput = document.getElementById("inspect-output");
    const autoRefreshToggle = document.getElementById("auto-refresh-toggle");
    const lastUpdatedBadge = document.getElementById("last-updated-badge");
    const logsUpdatedBadge = document.getElementById("logs-updated-badge");
    const healthSpinner = document.getElementById("health-spinner");
    const logsSpinner = document.getElementById("logs-spinner");
    const logViewer = document.getElementById("log-viewer-pre");
    const downloadLogsBtn = document.getElementById("download-logs-btn");
    const autoScrollToggle = document.getElementById("auto-scroll-toggle");
    const logFilterInput = document.getElementById("log-filter-input");

    let autoRefreshInterval = null;
    let isFetchingHealth = false;
    let isFetchingLogs = false;
    let currentLogs = [];

    function formatTime(date) {
        return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }

    async function loadHealth() {
        if (isFetchingHealth) return;
        isFetchingHealth = true;
        if (healthSpinner) healthSpinner.style.display = "inline-block";
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.textContent = "Updating...";
        }

        try {
            const res = await fetch("/api/diagnostics/health");
            if (!res.ok) throw new Error("Health check returned status " + res.status);
            const data = await res.json();

            // Status & Environment
            const statusEl = document.getElementById("diag-status");
            if (statusEl) statusEl.textContent = (data.status || "OK").toUpperCase();

            const memEl = document.getElementById("diag-memory");
            if (memEl && data.system) memEl.textContent = data.system.memory_rss_mb + " MB";

            const mirrorEl = document.getElementById("diag-active-mirror");
            if (mirrorEl && data.mirrors) mirrorEl.textContent = data.mirrors.active_mirror || "None";

            const cacheEl = document.getElementById("diag-cache");
            if (cacheEl && data.cache) {
                cacheEl.textContent = `${data.cache.details_cache_size} / ${data.cache.details_cache_max}`;
            }

            // Mirror Probes & Performance Rankings
            const mirrorContainer = document.getElementById("mirror-metrics");
            if (mirrorContainer) {
                mirrorContainer.innerHTML = "";
                const mirrorsList = [...(data.mirrors.mirrors || [])];
                // Sort mirrors by score descending
                mirrorsList.sort((a, b) => (b.score || 0) - (a.score || 0));

                mirrorsList.forEach((m, index) => {
                    const metric = document.createElement("div");
                    metric.className = "diag-metric";
                    const isParked = m.is_parked;
                    const isCooling = m.cooling_down && !isParked;
                    const latencyText = m.reachable ? `${m.latency_ms} ms` : "Offline";
                    const statusColor = isParked
                        ? "#ef4444"
                        : isCooling
                          ? "#f59e0b"
                          : m.reachable
                            ? "#4ade80"
                            : "#f87171";
                    const statusLabel = isParked
                        ? "Parked / Invalid"
                        : isCooling
                          ? "Cooldown"
                          : m.reachable
                            ? latencyText
                            : "Offline";
                    const isTopRanked = index < 3 && m.reachable && !isCooling && !isParked;
                    const rankBadgeColor = isTopRanked ? "#38bdf8" : "var(--text-muted, #94a3b8)";
                    const protoLabel = (m.protocol || "https").toUpperCase();
                    const protoColor = protoLabel === "HTTPS" ? "#38bdf8" : "#fbbf24";

                    metric.innerHTML = `
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <span class="diag-label" style="font-weight: 700; color: ${rankBadgeColor}">#${index + 1} Rank</span>
                            <div style="display: flex; gap: 4px; align-items: center;">
                                <span class="diag-badge" style="font-size: 0.7rem; padding: 2px 6px; color: ${protoColor}; border-color: ${protoColor}40;">${protoLabel}</span>
                                <span class="diag-badge" style="font-size: 0.75rem; padding: 2px 8px;">Score: ${m.score !== undefined ? m.score : "-"}</span>
                            </div>
                        </div>
                        <span class="diag-label" style="word-break: break-all; color: #fff; font-size: 0.9rem;">${m.hostname}</span>
                        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 6px;">
                            <span class="diag-val" style="color: ${statusColor}; font-size: 1.15rem;">
                                ${statusLabel}
                            </span>
                            <span style="font-size: 0.8rem; color: var(--text-muted, #94a3b8);">
                                Rate: ${m.success_rate || 0}%
                            </span>
                        </div>
                    `;
                    mirrorContainer.appendChild(metric);
                });
            }

            // Clients (Clean naming: no Strategy or Download Client suffixes)
            const clientContainer = document.getElementById("client-metrics");
            if (clientContainer) {
                clientContainer.innerHTML = "";
                (data.clients || []).forEach((c) => {
                    const metric = document.createElement("div");
                    metric.className = "diag-metric";
                    const statusText = c.status || (c.connected ? "Connected" : "Disconnected");
                    let statusColor = "#4ade80"; // green
                    if (statusText === "IP Banned") {
                        statusColor = "#ef4444"; // red
                    } else if (statusText === "Auth Failed" || statusText === "Auth Cooldown") {
                        statusColor = "#f59e0b"; // amber
                    } else if (!c.connected) {
                        statusColor = "#f87171"; // soft red
                    }

                    metric.innerHTML = `
                        <span class="diag-label">${c.name}</span>
                        <span class="diag-val" style="color: ${statusColor}; font-size: 1.15rem;">
                            ${statusText}
                        </span>
                        ${c.error ? `<span style="font-size: 0.78rem; color: #f87171; margin-top: 4px; word-break: break-word;">${c.error}</span>` : ""}
                    `;
                    clientContainer.appendChild(metric);
                });
            }

            if (lastUpdatedBadge) {
                lastUpdatedBadge.textContent = "Last updated: " + formatTime(new Date());
            }
        } catch (e) {
            console.error("Failed to load health metrics", e);
            if (lastUpdatedBadge) {
                lastUpdatedBadge.textContent = "Update failed: " + formatTime(new Date());
            }
        } finally {
            isFetchingHealth = false;
            if (healthSpinner) healthSpinner.style.display = "none";
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.textContent = "Refresh Health";
            }
        }
    }

    async function loadLogs() {
        if (!logViewer || isFetchingLogs) return;
        isFetchingLogs = true;
        if (logsSpinner) logsSpinner.style.display = "inline-block";
        if (refreshLogsBtn) {
            refreshLogsBtn.disabled = true;
            refreshLogsBtn.textContent = "Updating...";
        }

        try {
            const res = await fetch("/api/diagnostics/logs?limit=150");
            if (!res.ok) throw new Error("Logs check returned status " + res.status);
            const data = await res.json();
            currentLogs = data.logs || [];
            renderLogs();
            if (logsUpdatedBadge) {
                logsUpdatedBadge.textContent = "Last updated: " + formatTime(new Date());
            }
        } catch (e) {
            console.error("Failed to fetch logs", e);
            if (logsUpdatedBadge) {
                logsUpdatedBadge.textContent = "Update failed: " + formatTime(new Date());
            }
        } finally {
            isFetchingLogs = false;
            if (logsSpinner) logsSpinner.style.display = "none";
            if (refreshLogsBtn) {
                refreshLogsBtn.disabled = false;
                refreshLogsBtn.textContent = "Refresh Logs";
            }
        }
    }

    function renderLogs() {
        if (!logViewer) return;
        const filter = logFilterInput ? logFilterInput.value.trim().toLowerCase() : "";
        const lines = currentLogs.map((entry) => {
            if (typeof entry === "string") return entry;
            return entry && entry.message ? entry.message : JSON.stringify(entry);
        });
        const filtered = filter ? lines.filter((line) => line.toLowerCase().includes(filter)) : lines;

        logViewer.textContent = filtered.join("\n") || "(No logs recorded yet)";
        if (autoScrollToggle && autoScrollToggle.checked) {
            logViewer.scrollTop = logViewer.scrollHeight;
        }
    }

    async function runInspect() {
        if (!inspectInput || !inspectBtn || !inspectOutput) return;
        const val = inspectInput.value.trim();
        if (!val) return;

        inspectBtn.disabled = true;
        inspectOutput.style.display = "block";
        inspectOutput.textContent = "Inspecting parser...";

        try {
            const param =
                val.startsWith("http") || val.startsWith("/")
                    ? `url=${encodeURIComponent(val)}`
                    : `query=${encodeURIComponent(val)}`;
            const res = await fetch(`/api/diagnostics/inspect?${param}`);
            const json = await res.json();
            inspectOutput.textContent = JSON.stringify(json, null, 2);
        } catch (e) {
            inspectOutput.textContent = "Error: " + e.message;
        } finally {
            inspectBtn.disabled = false;
        }
    }

    function setupAutoRefresh() {
        if (autoRefreshToggle && autoRefreshToggle.checked) {
            if (!autoRefreshInterval) {
                autoRefreshInterval = setInterval(() => {
                    loadHealth();
                    loadLogs();
                }, 5000);
            }
        } else {
            if (autoRefreshInterval) {
                clearInterval(autoRefreshInterval);
                autoRefreshInterval = null;
            }
        }
    }

    if (refreshBtn) {
        refreshBtn.addEventListener("click", () => {
            loadHealth();
        });
    }

    if (refreshLogsBtn) {
        refreshLogsBtn.addEventListener("click", () => {
            loadLogs();
        });
    }

    if (inspectBtn) inspectBtn.addEventListener("click", runInspect);
    if (inspectInput) {
        inspectInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") runInspect();
        });
    }

    if (autoRefreshToggle) {
        autoRefreshToggle.addEventListener("change", setupAutoRefresh);
    }

    if (logFilterInput) {
        logFilterInput.addEventListener("input", renderLogs);
    }

    if (downloadLogsBtn) {
        downloadLogsBtn.addEventListener("click", () => {
            window.location.href = "/api/diagnostics/logs/download";
        });
    }

    // Initial load
    loadHealth();
    loadLogs();
    setupAutoRefresh();
});
