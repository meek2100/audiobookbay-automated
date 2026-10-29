// File: audiobook_automated/static/js/search.js
// app/static/js/search.js

// Define functions in the global scope (or attach to window) so tests and other scripts (actions.js) can use them.

// Expose these core functions to the global scope for testing and external use (e.g., actions.js)
window.parseFileSizeToMB = parseFileSizeToMB;
window.formatFileSize = formatFileSize;
window.initializeFilters = initializeFilters;
window.applyFilters = applyFilters;
window.clearFilters = clearFilters;
window.showLoadingSpinner = showLoadingSpinner;
window.hideLoadingSpinner = hideLoadingSpinner;
window.setViewMode = setViewMode;
window.initFloatingHud = initFloatingHud;
window.initTopFilterDrawer = initTopFilterDrawer;
window.syncHudFilters = syncHudFilters;
window.streamRemainingPages = streamRemainingPages;
window.createResultRowElement = createResultRowElement;
window.initHoverPrefetch = initHoverPrefetch;
window.initInfiniteScroll = initInfiniteScroll;
window.loadNextPage = loadNextPage;
window.resetPaginationState = resetPaginationState;

// Global variables defined in the file
let messageIndex = 0;
let intervalId = null;
const prefetchedQueries = new Set();
let currentPage = 1;
let isLoadingMore = false;
let hasMorePages = true;
let infiniteScrollObserver = null;

function resetPaginationState() {
    currentPage = 1;
    isLoadingMore = false;
    hasMorePages = true;
    if (infiniteScrollObserver) {
        infiniteScrollObserver.disconnect();
        infiniteScrollObserver = null;
    }
}

document.addEventListener("DOMContentLoaded", function () {
    // Initialize filtering if results are present
    if (document.querySelectorAll(".result-row").length > 0) {
        initializeFilters();
        const filterBtn = document.getElementById("filter-button");
        if (filterBtn) filterBtn.addEventListener("click", applyFilters);
        const clearBtn = document.getElementById("clear-button");
        if (clearBtn) clearBtn.addEventListener("click", clearFilters);
    }

    // Initialize View Mode (defaults to grid view)
    const savedView = localStorage.getItem("viewMode") || "grid";
    setViewMode(savedView);

    // Bind Toggle Buttons
    const listBtn = document.getElementById("view-list-btn");
    const gridBtn = document.getElementById("view-grid-btn");

    if (listBtn)
        listBtn.addEventListener("click", function () {
            setViewMode("list");
        });
    if (gridBtn)
        gridBtn.addEventListener("click", function () {
            setViewMode("grid");
        });

    // Search Form Handler
    const searchForm = document.getElementById("search-form");
    if (searchForm) {
        searchForm.addEventListener("submit", function () {
            showLoadingSpinner();
        });
    }

    // Initialize Top Filter Drawer & Floating HUD
    initTopFilterDrawer();
    initFloatingHud();

    // Infinite Scroll Auto-loader & Progressive Search Streaming
    const resultsContainer = document.getElementById("results-container");
    if (resultsContainer && resultsContainer.dataset.query && resultsContainer.dataset.hasResults === "true") {
        const query = resultsContainer.dataset.query;
        initInfiniteScroll(query);
    }

    initHoverPrefetch();
});

function setViewMode(mode) {
    const container = document.getElementById("results-container");
    const listBtn = document.getElementById("view-list-btn");
    const gridBtn = document.getElementById("view-grid-btn");

    if (!container || !listBtn || !gridBtn) return;

    // Update localStorage
    localStorage.setItem("viewMode", mode);

    // Update Container Class
    container.classList.remove("view-list", "view-grid");
    container.classList.add("view-" + mode);

    // Update Buttons
    if (mode === "list") {
        listBtn.classList.add("active");
        gridBtn.classList.remove("active");
    } else {
        gridBtn.classList.add("active");
        listBtn.classList.remove("active");
    }
}

// ROBUSTNESS: Handle Browser Back/Forward Cache (BFCache)
// If the user searches, navigates away, and clicks "Back", the page might load
// from cache with the spinner still active. This forces a reset.
window.addEventListener("pageshow", function (event) {
    if (event.persisted) {
        hideLoadingSpinner();
    }
});

// --- Helper Functions ---

/**
 * Initializes all filter components (Native Date and Size inputs).
 */
function initializeFilters() {
    // Native HTML5 inputs require no vendor initialization.
    // If needed, set date input constraints based on DOM rows.
    const dateFromEl = document.getElementById("date-from-filter");
    const dateToEl = document.getElementById("date-to-filter");

    if (dateFromEl && dateToEl) {
        // Clear any stale constraints or re-sync
        dateFromEl.addEventListener("change", () => {
            if (dateFromEl.value) {
                dateToEl.min = dateFromEl.value;
            } else {
                dateToEl.removeAttribute("min");
            }
        });
        dateToEl.addEventListener("change", () => {
            if (dateToEl.value) {
                dateFromEl.max = dateToEl.value;
            } else {
                dateFromEl.removeAttribute("max");
            }
        });
    }
}

/**
 * Parses a file size string (e.g., "1.5 GB") into Megabytes.
 * @param {string} sizeString - The file size string.
 * @returns {number|null} - Size in MB or null if invalid.
 */
function parseFileSizeToMB(sizeString) {
    if (!sizeString || sizeString.trim().toLowerCase() === "unknown") return null;

    const match = sizeString.trim().match(/^(\d+(?:\.\d+)?)\s*([a-zA-Z]+)$/);
    if (!match) return null;

    const size = parseFloat(match[1]);
    const unit = match[2].toUpperCase();

    if (isNaN(size)) return null;

    if (unit.startsWith("PB")) return size * 1024 * 1024 * 1024;
    if (unit.startsWith("TB")) return size * 1024 * 1024;
    if (unit.startsWith("GB")) return size * 1024;
    if (unit.startsWith("KB")) return size / 1024;
    if (unit.startsWith("B")) return size / (1024 * 1024);

    if (unit.startsWith("MB")) return size;

    console.warn("Unrecognized file size unit:", unit, "in string:", sizeString);
    return size;
}

/**
 * Formats a size in MB to a human-readable string (MB/GB/TB).
 * @param {number} mb - Size in Megabytes.
 * @returns {string} - Formatted string.
 */
function formatFileSize(mb) {
    if (mb === null || isNaN(mb)) return "Unknown";
    if (mb >= 1024 * 1024) {
        return (mb / (1024 * 1024)).toFixed(2) + " TB";
    }
    if (mb >= 1024) {
        return (mb / 1024).toFixed(2) + " GB";
    }
    return mb.toFixed(2) + " MB";
}

/**
 * Parses any date format string from AudiobookBay or ISO into a Date object at midnight UTC.
 * @param {string} dateStr - Date string.
 * @returns {Date|null}
 */
function parsePostDate(dateStr) {
    if (!dateStr || dateStr === "Unknown") return null;
    try {
        let date;
        if (/^\d{1,2}\s[a-zA-Z]{3}\s\d{4}$/.test(dateStr)) {
            const formattedStr = dateStr.replace(/(\d{1,2})\s(\w{3})\s(\d{4})/, "$2 $1, $3");
            date = new Date(formattedStr);
        } else if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
            date = new Date(dateStr + "T00:00:00");
        } else {
            date = new Date(dateStr);
        }
        return isNaN(date.getTime()) ? null : date;
    } catch {
        return null;
    }
}

/**
 * Applies all active filters to the result table.
 */
function applyFilters() {
    const category = document.getElementById("category-filter")?.value || "";
    const language = document.getElementById("language-filter")?.value || "";
    const bitrate = document.getElementById("bitrate-filter")?.value || "";
    const format = document.getElementById("format-filter")?.value || "";
    const fileSizeFilter = document.getElementById("file-size-filter")?.value || "";

    const dateFromVal = document.getElementById("date-from-filter")?.value || "";
    const dateToVal = document.getElementById("date-to-filter")?.value || "";

    const dateFrom = dateFromVal ? new Date(dateFromVal + "T00:00:00") : null;
    const dateTo = dateToVal ? new Date(dateToVal + "T23:59:59") : null;

    document.querySelectorAll(".result-row").forEach((row) => {
        let visible = true;

        // Exact Token Match for Category
        if (category) {
            const rowCategories = (row.dataset.category || "").split("|").map((t) => t.trim());
            if (!rowCategories.includes(category)) {
                visible = false;
            }
        }

        if (language && row.dataset.language !== language) visible = false;
        if (bitrate && row.dataset.bitrate !== bitrate) visible = false;
        if (format && row.dataset.format !== format) visible = false;

        // File size filter presets
        if (fileSizeFilter) {
            const rowSizeMB = parseFileSizeToMB(row.dataset.fileSize);
            if (rowSizeMB === null) {
                visible = false;
            } else if (fileSizeFilter === "under_500mb" && rowSizeMB >= 500) {
                visible = false;
            } else if (fileSizeFilter === "500mb_2gb" && (rowSizeMB < 500 || rowSizeMB > 2048)) {
                visible = false;
            } else if (fileSizeFilter === "2gb_5gb" && (rowSizeMB < 2048 || rowSizeMB > 5120)) {
                visible = false;
            } else if (fileSizeFilter === "over_5gb" && rowSizeMB < 5120) {
                visible = false;
            }
        }

        // Native Date Range filter
        if (dateFrom || dateTo) {
            const rowDate = parsePostDate(row.dataset.postDate);
            if (!rowDate) {
                visible = false;
            } else {
                if (dateFrom && rowDate < dateFrom) visible = false;
                if (dateTo && rowDate > dateTo) visible = false;
            }
        }

        row.style.display = visible ? "" : "none";
    });
}

/**
 * Resets all filters to their default state.
 */
function clearFilters() {
    const fields = [
        "category-filter",
        "language-filter",
        "bitrate-filter",
        "format-filter",
        "file-size-filter",
        "date-from-filter",
        "date-to-filter",
    ];

    fields.forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.value = "";
    });

    const dateFromEl = document.getElementById("date-from-filter");
    const dateToEl = document.getElementById("date-to-filter");
    if (dateFromEl) dateFromEl.removeAttribute("max");
    if (dateToEl) dateToEl.removeAttribute("min");

    document.querySelectorAll(".result-row").forEach((row) => {
        row.style.display = "";
    });
}

/**
 * Shows the loading spinner and initializes the funny message scroller.
 */
function showLoadingSpinner() {
    const button = document.querySelector(".search-button");
    if (button) {
        button.disabled = true;
        if (!button.dataset.originalText) {
            // FIX: Use textContent instead of innerText for JSDOM compatibility
            button.dataset.originalText = button.querySelector(".button-text").textContent;
        }
        button.querySelector(".button-text").textContent = "Searching...";
    }

    const buttonSpinner = document.getElementById("button-spinner");
    if (buttonSpinner) buttonSpinner.style.display = "inline-block";

    setTimeout(showScrollingMessages, 3000);
}

/**
 * Hides the loading spinner and stops the message scroller.
 */
function hideLoadingSpinner() {
    const button = document.querySelector(".search-button");
    if (button) {
        button.disabled = false;
        if (button.dataset.originalText) {
            // FIX: Use textContent instead of innerText for JSDOM compatibility
            button.querySelector(".button-text").textContent = button.dataset.originalText;
        }
    }

    const buttonSpinner = document.getElementById("button-spinner");
    if (buttonSpinner) buttonSpinner.style.display = "none";

    hideScrollingMessages();
}

const messages = [
    "Searching... This better be worth it!",
    "Hold on, this takes a while...",
    "Still searching... Maybe grab a snack?",
    "Patience, young grasshopper...",
    "Wow, this is taking a minute!",
    "Finding the best results for you!",
    "Hang tight! Searching magic happening!",
    "One moment... while I consult the ancients.",
    "Beep boop... processing... please wait...",
    "My hamsters are running on a wheel, almost there!",
    "Almost there... just defragmenting my brain.",
    "Searching... because the internet is a big place!",
    "The search is strong with this one.",
    "Searching in hyperspace... almost there!",
    "Just a few more gigabytes to process...",
];

function showScrollingMessages() {
    const messageScroller = document.getElementById("message-scroller");
    const scrollingMessage = document.getElementById("scrolling-message");
    if (!scrollingMessage) return;

    const shuffledMessages = messages.sort(() => Math.random() - 0.5);
    messageScroller.style.display = "block";
    scrollingMessage.textContent = shuffledMessages[messageIndex];

    if (intervalId) clearInterval(intervalId);
    intervalId = setInterval(() => {
        messageIndex = (messageIndex + 1) % messages.length;
        scrollingMessage.textContent = shuffledMessages[messageIndex];
    }, 4000);
}

function hideScrollingMessages() {
    const messageScroller = document.getElementById("message-scroller");
    if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
    }
    if (messageScroller) messageScroller.style.display = "none";
}

/**
 * Escapes HTML entities to prevent XSS.
 * @param {string} str - Raw string.
 * @returns {string} - Escaped string.
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

/**
 * Creates a DOM table row for a book summary.
 * @param {Object} book - The BookSummary dictionary.
 * @returns {HTMLTableRowElement} - The created .result-row element.
 */
function createResultRowElement(book) {
    const row = document.createElement("tr");
    row.className = "result-row";
    row.dataset.category = Array.isArray(book.category) ? book.category.join("|") : book.category || "";
    row.dataset.language = book.language || "Unknown";
    row.dataset.bitrate = book.bitrate || "Unknown";
    row.dataset.format = book.format || "Unknown";
    row.dataset.fileSize = book.file_size || "Unknown";
    row.dataset.postDate = book.post_date || "Unknown";

    const defaultCover =
        document.querySelector(".cover[data-default-cover]")?.getAttribute("data-default-cover") ||
        "/static/images/audiobook-default-cover.png";
    const coverSrc = book.cover ? escapeHtml(book.cover) : defaultCover;
    const detailsUrl = "/details?link=" + encodeURIComponent(book.link || "");
    const title = escapeHtml(book.title || "Untitled Audiobook");

    // Category pills HTML
    let categoryHtml = "";
    if (Array.isArray(book.category)) {
        book.category.forEach((rawCat) => {
            const parts = rawCat.split(",");
            parts.forEach((cat) => {
                const clean = cat.trim();
                if (clean && clean !== "Unknown") {
                    categoryHtml += `<a href="/?query=${encodeURIComponent("type:" + clean)}" class="category-tag category-link" title="Browse ${escapeHtml(clean)} category">${escapeHtml(clean)}</a>\n`;
                }
            });
        });
    }

    row.innerHTML = `
        <td class="col-cover">
            <a href="${detailsUrl}">
                <img src="${coverSrc}" alt="Cover Art" class="cover" width="100" loading="lazy" decoding="async" data-default-cover="${defaultCover}" />
            </a>
        </td>
        <td class="col-info">
            <p class="book-title">${title}</p>
            <div class="categories-container">
                ${categoryHtml}
            </div>
            <div class="property-results-container">
                <span class="book-language">Language: ${escapeHtml(book.language || "Unknown")}</span>
                <span class="book-bitrate">Bitrate: ${escapeHtml(book.bitrate || "Unknown")}</span>
                <span class="book-format">Format: ${escapeHtml(book.format || "Unknown")}</span>
                <span class="book-file_size">File Size: ${escapeHtml(book.file_size || "Unknown")}</span>
                <span class="book-post_date">Posted: ${escapeHtml(book.post_date || "Unknown")}</span>
            </div>
        </td>
        <td class="col-actions">
            <div class="action-buttons">
                <a href="${detailsUrl}" class="btn-glass details-button">Details</a>
                <button class="btn-primary send-torrent-btn" data-link="${escapeHtml(book.link || "")}" data-title="${title}">Download</button>
            </div>
        </td>
    `;
    return row;
}

/**
 * Loads the next page of search results asynchronously and appends to the table.
 * @param {string} query - The search query term.
 * @returns {Promise<boolean>} - True if more results might exist, false if exhausted or errored.
 */
function showEndOfResults() {
    const indicator = document.getElementById("load-more-indicator");
    const endNote = document.getElementById("load-more-end");
    if (indicator) indicator.style.display = "none";
    if (endNote) endNote.style.display = "block";
}

async function loadNextPage(query) {
    if (isLoadingMore || !hasMorePages || !query) return false;

    const indicator = document.getElementById("load-more-indicator");
    const loadingSpinner = document.getElementById("load-more-loading");
    const loadMoreBtn = document.getElementById("load-more-btn");
    const tbody = document.getElementById("results-table-body");
    if (!tbody) return false;

    isLoadingMore = true;
    if (indicator) indicator.style.display = "flex";
    if (loadingSpinner) loadingSpinner.style.display = "flex";
    if (loadMoreBtn) loadMoreBtn.style.display = "none";

    const nextPage = currentPage + 1;

    try {
        const response = await fetch(`/api/search?query=${encodeURIComponent(query)}&page=${nextPage}`);
        if (!response.ok) {
            hasMorePages = false;
            if (indicator) indicator.style.display = "none";
            return false;
        }

        const data = await response.json();
        if (!data.books || data.books.length === 0) {
            hasMorePages = false;
            showEndOfResults();
            return false;
        }

        // Append rows
        data.books.forEach((book) => {
            const row = createResultRowElement(book);
            tbody.appendChild(row);
        });

        currentPage = nextPage;
        hasMorePages = Boolean(data.has_more);

        // Re-apply hover prefetching and filter evaluation on newly inserted rows
        initHoverPrefetch();
        applyFilters();

        if (!hasMorePages) {
            showEndOfResults();
        } else {
            // Keep indicator visible so IntersectionObserver can trigger subsequent pages when user scrolls
            if (loadingSpinner) loadingSpinner.style.display = "none";
            if (loadMoreBtn) loadMoreBtn.style.display = "inline-block";
            // IntersectionObserver only fires on visibility changes: re-observe so a sentinel that is
            // still on screen after this page keeps loading automatically (the button is only a fallback).
            if (infiniteScrollObserver && indicator) {
                infiniteScrollObserver.unobserve(indicator);
                infiniteScrollObserver.observe(indicator);
            }
        }

        return hasMorePages;
    } catch (err) {
        console.warn("Infinite scroll page load interrupted:", err);
        hasMorePages = false;
        if (indicator) indicator.style.display = "none";
        return false;
    } finally {
        isLoadingMore = false;
    }
}

/**
 * Initializes continuous scroll-triggered auto-loading using IntersectionObserver.
 * @param {string} query - Search term.
 */
function initInfiniteScroll(query) {
    currentPage = 1;
    isLoadingMore = false;
    hasMorePages = true;

    const indicator = document.getElementById("load-more-indicator");
    const loadMoreBtn = document.getElementById("load-more-btn");

    if (indicator) {
        indicator.style.display = "flex";
    }

    if (loadMoreBtn) {
        loadMoreBtn.addEventListener("click", () => {
            loadNextPage(query);
        });
    }

    // Set up IntersectionObserver if supported
    if ("IntersectionObserver" in window && indicator) {
        if (infiniteScrollObserver) {
            infiniteScrollObserver.disconnect();
        }

        infiniteScrollObserver = new IntersectionObserver(
            (entries) => {
                const entry = entries[0];
                if (entry && entry.isIntersecting && !isLoadingMore && hasMorePages) {
                    loadNextPage(query);
                }
            },
            {
                root: null,
                rootMargin: "300px",
                threshold: 0.1,
            }
        );

        infiniteScrollObserver.observe(indicator);
    } else {
        // Fallback for environments without IntersectionObserver: stream up to 5 pages
        streamRemainingPages(query, 2, 5);
    }
}

/**
 * Streams remaining search result pages sequentially (fallback or testing helper).
 * @param {string} query - The search keyword.
 * @param {number} startPage - The starting background page (typically 2).
 * @param {number} maxPage - The maximum background page to fetch (typically 5).
 */
async function streamRemainingPages(query, startPage = 2, maxPage = 5) {
    const indicator = document.getElementById("load-more-indicator");
    const tbody = document.getElementById("results-table-body");
    if (!tbody || !query) return;

    if (indicator) indicator.style.display = "flex";

    for (let page = startPage; page <= maxPage; page++) {
        try {
            const response = await fetch(`/api/search?query=${encodeURIComponent(query)}&page=${page}`);
            if (!response.ok) {
                break;
            }
            const data = await response.json();
            if (!data.books || data.books.length === 0) {
                break;
            }

            // Append rows
            data.books.forEach((book) => {
                const row = createResultRowElement(book);
                tbody.appendChild(row);
            });

            // Re-apply hover prefetching and filter evaluation
            initHoverPrefetch();
            applyFilters();

            currentPage = page;
            if (!data.has_more) {
                hasMorePages = false;
                break;
            }
        } catch (err) {
            console.warn("Background streaming interrupted:", err);
            break;
        }
    }

    if (!hasMorePages) {
        showEndOfResults();
    } else if (indicator) {
        indicator.style.display = "none";
    }
}

/**
 * Prefetches search results or book details into browser cache and server cache.
 * @param {string} url - The URL to prefetch.
 */
function prefetchUrl(url) {
    if (!url || prefetchedQueries.has(url)) return;
    prefetchedQueries.add(url);

    // Use low priority background fetch
    fetch(url, { priority: "low" }).catch(() => {});
}

/**
 * Initializes hover prefetching for all Category, Author, Narrator, and Details links.
 * When the user hovers for 120ms, or when results scroll into view, a prefetch request is sent to warm caches.
 */
function initHoverPrefetch() {
    // 1. Prefetch Category & Search links
    const categoryLinks = document.querySelectorAll("a.category-link");
    categoryLinks.forEach((link) => {
        if (link.dataset.prefetchBound) return;
        link.dataset.prefetchBound = "true";

        let hoverTimer = null;
        link.addEventListener("mouseenter", function () {
            const href = link.getAttribute("href");
            if (!href || !href.includes("query=")) return;
            const match = href.match(/[?&]query=([^&]+)/);
            if (!match) return;
            const query = decodeURIComponent(match[1].replace(/\+/g, " ")).trim();
            if (query.length < 2 || prefetchedQueries.has(query)) return;

            hoverTimer = setTimeout(() => {
                prefetchUrl(`/api/search?query=${encodeURIComponent(query)}&page=1`);
            }, 120);
        });

        link.addEventListener("mouseleave", function () {
            if (hoverTimer) {
                clearTimeout(hoverTimer);
                hoverTimer = null;
            }
        });
    });

    // 2. Prefetch Details links for fast private view loading
    const detailsLinks = document.querySelectorAll("a.details-button, .col-cover a");
    detailsLinks.forEach((link) => {
        if (link.dataset.prefetchBound) return;
        link.dataset.prefetchBound = "true";

        let hoverTimer = null;
        link.addEventListener("mouseenter", function () {
            const href = link.getAttribute("href");
            if (!href || !href.includes("link=")) return;

            hoverTimer = setTimeout(() => {
                prefetchUrl(href);
            }, 120);
        });

        link.addEventListener("mouseleave", function () {
            if (hoverTimer) {
                clearTimeout(hoverTimer);
                hoverTimer = null;
            }
        });
    });
}

/**
 * Syncs the quick HUD filter dropdowns with the main filter container controls,
 * and updates the active filter count badge.
 */
function syncHudFilters(fromHud = false) {
    const fields = ["category", "language", "bitrate", "format", "file-size"];
    let activeFilterCount = 0;

    fields.forEach((field) => {
        const mainEl = document.getElementById(`${field}-filter`);
        const hudEl = document.getElementById(`hud-${field}-filter`);
        if (!mainEl || !hudEl) return;

        if (fromHud) {
            mainEl.value = hudEl.value;
        } else {
            hudEl.value = mainEl.value;
        }

        if (mainEl.value) {
            activeFilterCount++;
        }
    });

    // Check date inputs for active filter count
    const dateFrom = document.getElementById("date-from-filter")?.value;
    const dateTo = document.getElementById("date-to-filter")?.value;
    if (dateFrom || dateTo) {
        activeFilterCount++;
    }

    // Update active filter badges on both toolbar and floating HUD
    const hudBadge = document.getElementById("hud-filter-badge");
    if (hudBadge) {
        if (activeFilterCount > 0) {
            hudBadge.textContent = activeFilterCount;
            hudBadge.style.display = "inline-block";
        } else {
            hudBadge.style.display = "none";
        }
    }

    const toolbarBadge = document.getElementById("toolbar-filter-badge");
    if (toolbarBadge) {
        if (activeFilterCount > 0) {
            toolbarBadge.textContent = activeFilterCount;
            toolbarBadge.style.display = "inline-block";
        } else {
            toolbarBadge.style.display = "none";
        }
    }

    const toolbarClearBtn = document.getElementById("toolbar-clear-btn");
    if (toolbarClearBtn) {
        toolbarClearBtn.style.display = activeFilterCount > 0 ? "inline-block" : "none";
    }
}

/**
 * Initializes the floating condensed HUD bar that slides into view upon scrolling.
 */
function initFloatingHud() {
    const hud = document.getElementById("floating-filter-hud");
    if (!hud) return;

    const hudFilterToggle = document.getElementById("hud-filter-toggle");
    const hudFilterDrawer = document.getElementById("hud-filter-drawer");
    const hudDrawerClose = document.getElementById("hud-drawer-close");
    const hudApplyBtn = document.getElementById("hud-apply-filters-btn");
    const hudClearBtn = document.getElementById("hud-clear-filters-btn");
    const hudTopBtn = document.getElementById("hud-top-btn");
    const hudSearchForm = document.getElementById("hud-search-form");
    const hudSearchInput = document.getElementById("hud-search-input");
    const mainSearchInput = document.querySelector(".search-bar");

    // Scroll listener for HUD visibility
    let ticking = false;
    const indicator = document.getElementById("load-more-indicator");

    const onScroll = () => {
        const scrollThreshold = 350;
        if (window.scrollY > scrollThreshold) {
            hud.classList.add("visible");
        } else {
            hud.classList.remove("visible");
            if (hudFilterDrawer) {
                hudFilterDrawer.classList.remove("open");
                hudFilterDrawer.setAttribute("aria-hidden", "true");
            }
        }
        ticking = false;
    };

    window.addEventListener(
        "scroll",
        () => {
            if (!ticking) {
                ticking = true;
                window.requestAnimationFrame(onScroll);
            }
        },
        { passive: true }
    );

    // Initial check in case page starts scrolled
    onScroll();

    // Toggle filter drawer
    if (hudFilterToggle && hudFilterDrawer) {
        hudFilterToggle.addEventListener("click", (e) => {
            e.stopPropagation();
            syncHudFilters(false);
            const isOpen = hudFilterDrawer.classList.toggle("open");
            hudFilterDrawer.setAttribute("aria-hidden", (!isOpen).toString());
        });
    }

    // Close filter drawer button
    if (hudDrawerClose && hudFilterDrawer) {
        hudDrawerClose.addEventListener("click", () => {
            hudFilterDrawer.classList.remove("open");
            hudFilterDrawer.setAttribute("aria-hidden", "true");
        });
    }

    // Close drawer when clicking outside
    document.addEventListener("click", (e) => {
        if (hudFilterDrawer && hudFilterDrawer.classList.contains("open")) {
            if (!hudFilterDrawer.contains(e.target) && !hudFilterToggle.contains(e.target)) {
                hudFilterDrawer.classList.remove("open");
                hudFilterDrawer.setAttribute("aria-hidden", "true");
            }
        }
    });

    // Apply HUD filters
    if (hudApplyBtn) {
        hudApplyBtn.addEventListener("click", () => {
            syncHudFilters(true);
            applyFilters();
            if (hudFilterDrawer) {
                hudFilterDrawer.classList.remove("open");
                hudFilterDrawer.setAttribute("aria-hidden", "true");
            }
        });
    }

    // Clear HUD filters
    if (hudClearBtn) {
        hudClearBtn.addEventListener("click", () => {
            clearFilters();
            syncHudFilters(false);
            if (hudFilterDrawer) {
                hudFilterDrawer.classList.remove("open");
                hudFilterDrawer.setAttribute("aria-hidden", "true");
            }
        });
    }

    // Jump to top from HUD
    if (hudTopBtn) {
        hudTopBtn.addEventListener("click", () => {
            window.scrollTo({
                top: 0,
                behavior: "smooth",
            });
        });
    }

    // Synchronize HUD search form submit with main search form spinner
    if (hudSearchForm) {
        hudSearchForm.addEventListener("submit", () => {
            if (mainSearchInput && hudSearchInput) {
                mainSearchInput.value = hudSearchInput.value;
            }
            showLoadingSpinner();
        });
    }

    // Also sync badge whenever main filters change
    const filterBtn = document.getElementById("filter-button");
    if (filterBtn) {
        filterBtn.addEventListener("click", () => syncHudFilters(false));
    }
    const clearBtn = document.getElementById("clear-button");
    if (clearBtn) {
        clearBtn.addEventListener("click", () => syncHudFilters(false));
    }
}

/**
 * Initializes the top toolbar expanding filter drawer modal overlay.
 */
function initTopFilterDrawer() {
    const toggleBtn = document.getElementById("toolbar-filter-toggle");
    const overlay = document.getElementById("filter-drawer-overlay");
    const closeBtn = document.getElementById("filter-drawer-close");
    const applyBtn = document.getElementById("filter-button");
    const clearBtn = document.getElementById("clear-button");
    const toolbarClearBtn = document.getElementById("toolbar-clear-btn");

    if (!toggleBtn || !overlay) return;

    const openDrawer = () => {
        overlay.classList.add("open");
        overlay.setAttribute("aria-hidden", "false");
    };

    const closeDrawer = () => {
        overlay.classList.remove("open");
        overlay.setAttribute("aria-hidden", "true");
    };

    toggleBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        openDrawer();
    });

    if (closeBtn) {
        closeBtn.addEventListener("click", closeDrawer);
    }

    // Close when clicking backdrop outside card
    overlay.addEventListener("click", (e) => {
        if (e.target === overlay) {
            closeDrawer();
        }
    });

    // Close when pressing Escape key
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && overlay.classList.contains("open")) {
            closeDrawer();
        }
    });

    // Auto-close overlay after applying filters
    if (applyBtn) {
        applyBtn.addEventListener("click", () => {
            closeDrawer();
            syncHudFilters(false);
        });
    }

    // Toolbar clear button directly resets filters
    if (toolbarClearBtn) {
        toolbarClearBtn.addEventListener("click", () => {
            clearFilters();
            syncHudFilters(false);
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener("click", () => {
            syncHudFilters(false);
        });
    }
}
