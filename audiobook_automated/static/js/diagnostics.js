// File: audiobook_automated/static/js/diagnostics.js
/**
 * Real-time Diagnostics Dashboard Controller
 * Handles auto-refresh, badge updates, logs streaming, and log file download.
 */

document.addEventListener("DOMContentLoaded", () => {
    const refreshBtn = document.getElementById("refresh-diag-btn");
    const inspectBtn = document.getElementById("run-inspect-btn");
    const inspectInput = document.getElementById("inspect-input");
    const inspectOutput = document.getElementById("inspect-output");
    const autoRefreshToggle = document.getElementById("auto-refresh-toggle");
    const lastUpdatedBadge = document.getElementById("last-updated-badge");
    const logViewer = document.getElementById("log-viewer-pre");
    const downloadLogsBtn = document.getElementById("download-logs-btn");
    const autoScrollToggle = document.getElementById("auto-scroll-toggle");
    const logFilterInput = document.getElementById("log-filter-input");

    let autoRefreshInterval = null;
    let isFetchingHealth = false;
    let currentLogs = [];

    function formatTime(date) {
        return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }

    async function loadHealth() {
        if (isFetchingHealth) return;
        isFetchingHealth = true;
        if (refreshBtn) {
            refreshBtn.classList.add("refreshing");
            refreshBtn.disabled = true;
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

            // Mirror Probes & Performance
            const mirrorContainer = document.getElementById("mirror-metrics");
            if (mirrorContainer) {
                mirrorContainer.innerHTML = "";
                (data.mirrors.mirrors || []).forEach((m) => {
                    const metric = document.createElement("div");
                    metric.className = "diag-metric";
                    const isCooling = m.cooling_down;
                    const latencyText = m.reachable ? `${m.latency_ms} ms` : "Offline";
                    const statusColor = isCooling ? "#f59e0b" : m.reachable ? "#4ade80" : "#f87171";
                    const statusLabel = isCooling ? "Cooldown" : m.reachable ? latencyText : "Offline";

                    metric.innerHTML = `
                        <span class="diag-label">${m.hostname} (Rate: ${m.success_rate || 100}%)</span>
                        <span class="diag-val" style="color: ${statusColor}; font-size: 1.05rem;">
                            ${statusLabel}
                        </span>
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
                    metric.innerHTML = `
                        <span class="diag-label">${c.name}</span>
                        <span class="diag-val" style="color: ${c.connected ? "#4ade80" : "#f87171"}; font-size: 1.05rem;">
                            ${c.connected ? "Connected" : "Disconnected"}
                        </span>
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
            if (refreshBtn) {
                refreshBtn.classList.remove("refreshing");
                refreshBtn.disabled = false;
            }
        }
    }

    async function loadLogs() {
        if (!logViewer) return;
        try {
            const res = await fetch("/api/diagnostics/logs?limit=150");
            if (!res.ok) return;
            const data = await res.json();
            currentLogs = data.logs || [];
            renderLogs();
        } catch (e) {
            console.error("Failed to fetch logs", e);
        }
    }

    function renderLogs() {
        if (!logViewer) return;
        const filter = logFilterInput ? logFilterInput.value.trim().toLowerCase() : "";
        const filtered = filter ? currentLogs.filter((line) => line.toLowerCase().includes(filter)) : currentLogs;

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
