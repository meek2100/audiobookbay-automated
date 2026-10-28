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
window.streamRemainingPages = streamRemainingPages;
window.createResultRowElement = createResultRowElement;
window.initHoverPrefetch = initHoverPrefetch;

// Global variables defined in the file
let datePicker;
let fileSizeSlider;
let messageIndex = 0;
let intervalId = null;
const prefetchedQueries = new Set();

document.addEventListener("DOMContentLoaded", function () {
    // Initialize filtering if results are present
    if (document.querySelectorAll(".result-row").length > 0) {
        initializeFilters();
        const filterBtn = document.getElementById("filter-button");
        if (filterBtn) filterBtn.addEventListener("click", applyFilters);
        const clearBtn = document.getElementById("clear-button");
        if (clearBtn) clearBtn.addEventListener("click", clearFilters);
    }

    // Initialize View Mode
    const savedView = localStorage.getItem("viewMode") || "list";
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

    // Progressive Search Streaming & Hover Prefetch
    const resultsContainer = document.getElementById("results-container");
    if (resultsContainer && resultsContainer.dataset.query && resultsContainer.dataset.hasResults === "true") {
        const query = resultsContainer.dataset.query;
        streamRemainingPages(query, 2, 5);
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
 * Initializes all filter components (Selects, Date Picker, Slider).
 */
function initializeFilters() {
    // RESILIENCE: Ensure vendor libraries are loaded before attempting initialization
    if (typeof flatpickr === "undefined" || typeof noUiSlider === "undefined") {
        console.error("Vendor libraries (flatpickr/noUiSlider) are missing. Filters disabled.");
        return;
    }

    // Optimization: populateSelectFilters() removed. Filters are now populated server-side.
    initializeFileSizeSlider();
    initializeDateRangePicker();
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
 * Initializes the Flatpickr date range input.
 */
function initializeDateRangePicker() {
    const allDates = Array.from(document.querySelectorAll(".result-row"))
        .map((row) => {
            const dateStr = row.dataset.postDate;
            if (!dateStr || dateStr === "Unknown") return null;
            try {
                let date;
                // Robust Date Parsing Strategy
                // Format 1: "01 Jan 2024" (AudiobookBay Default)
                if (/^\d{1,2}\s[a-zA-Z]{3}\s\d{4}$/.test(dateStr)) {
                    const formattedStr = dateStr.replace(/(\d{1,2})\s(\w{3})\s(\d{4})/, "$2 $1, $3");
                    date = new Date(formattedStr);
                }
                // Format 2: ISO 8601 "2024-01-01" (Standard Fallback/Change)
                else if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
                    date = new Date(dateStr);
                }
                // Format 3: Fallback to browser parsing (e.g. "Jan 1, 2024")
                else {
                    date = new Date(dateStr);
                }

                return isNaN(date.getTime()) ? null : date;
            } catch (e) {
                console.warn("Date parsing error for:", dateStr, e);
                return null;
            }
        })
        .filter((date) => date !== null);

    let options = {
        mode: "range",
        dateFormat: "Y-m-d",
    };

    if (allDates.length > 0) {
        const minDate = new Date(Math.min.apply(null, allDates));
        const maxDate = new Date(Math.max.apply(null, allDates));
        options.minDate = minDate;
        options.maxDate = maxDate;
    }

    datePicker = flatpickr("#date-range-filter", options);
}

/**
 * Initializes the noUiSlider for file size filtering.
 */
function initializeFileSizeSlider() {
    const sliderElement = document.getElementById("file-size-slider");
    const allSizes = Array.from(document.querySelectorAll(".result-row"))
        .map((row) => parseFileSizeToMB(row.dataset.fileSize))
        .filter((size) => size !== null);

    if (allSizes.length < 2) {
        const wrapper = document.querySelector(".file-size-filter-wrapper");
        if (wrapper) wrapper.style.display = "none";
        return;
    }

    const minSize = Math.min(...allSizes);
    const maxSize = Math.max(...allSizes);

    const formatter = {
        to: function (value) {
            return formatFileSize(value);
        },
        from: function (value) {
            return Number(parseFileSizeToMB(value));
        },
    };

    fileSizeSlider = noUiSlider.create(sliderElement, {
        start: [minSize, maxSize],
        connect: true,
        tooltips: [formatter, formatter],
        range: { min: minSize, max: maxSize },
    });
}

/**
 * Applies all active filters to the result table.
 */
function applyFilters() {
    const category = document.getElementById("category-filter").value;
    const language = document.getElementById("language-filter").value;
    const bitrate = document.getElementById("bitrate-filter").value;
    const format = document.getElementById("format-filter").value;
    const selectedDates = datePicker ? datePicker.selectedDates : [];
    const sizeRange = fileSizeSlider ? fileSizeSlider.get().map(parseFloat) : null;

    document.querySelectorAll(".result-row").forEach((row) => {
        let visible = true;

        // Exact Token Match for Category
        if (category) {
            const rowCategories = row.dataset.category.split("|").map((t) => t.trim());
            if (!rowCategories.includes(category)) {
                visible = false;
            }
        }

        if (language && row.dataset.language !== language) visible = false;
        if (bitrate && row.dataset.bitrate !== bitrate) visible = false;
        if (format && row.dataset.format !== format) visible = false;

        if (sizeRange) {
            const rowSizeMB = parseFileSizeToMB(row.dataset.fileSize);
            if (rowSizeMB === null || rowSizeMB < sizeRange[0] || rowSizeMB > sizeRange[1]) {
                visible = false;
            }
        }

        if (selectedDates.length === 2) {
            const rowDateStr = row.dataset.postDate;
            if (!rowDateStr || rowDateStr === "Unknown") {
                visible = false;
            } else {
                try {
                    let rowDate;
                    if (/^\d{1,2}\s[a-zA-Z]{3}\s\d{4}$/.test(rowDateStr)) {
                        const formattedStr = rowDateStr.replace(/(\d{1,2})\s(\w{3})\s(\d{4})/, "$2 $1, $3");
                        rowDate = new Date(formattedStr);
                    } else if (/^\d{4}-\d{2}-\d{2}$/.test(rowDateStr)) {
                        rowDate = new Date(rowDateStr);
                    } else {
                        rowDate = new Date(rowDateStr);
                    }

                    if (!isNaN(rowDate.getTime())) {
                        rowDate.setHours(0, 0, 0, 0);
                        if (rowDate < selectedDates[0] || rowDate > selectedDates[1]) {
                            visible = false;
                        }
                    } else {
                        visible = false;
                    }
                } catch (e) {
                    visible = false;
                }
            }
        }

        row.style.display = visible ? "" : "none";
    });
}

/**
 * Resets all filters to their default state.
 */
function clearFilters() {
    document.getElementById("category-filter").value = "";
    document.getElementById("language-filter").value = "";
    document.getElementById("bitrate-filter").value = "";
    document.getElementById("format-filter").value = "";
    if (datePicker) datePicker.clear();
    if (fileSizeSlider) fileSizeSlider.reset();

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
                    categoryHtml += `<a href="/?query=${encodeURIComponent(clean)}" class="category-tag category-link" title="Search ${escapeHtml(clean)} audiobooks">${escapeHtml(clean)}</a>\n`;
                }
            });
        });
    }

    row.innerHTML = `
        <td class="col-cover">
            <a href="${detailsUrl}">
                <img src="${coverSrc}" alt="Cover Art" class="cover" width="100" data-default-cover="${defaultCover}" />
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
 * Streams remaining search result pages sequentially in the background.
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

            // Re-apply hover prefetching and refresh filter dropdowns
            initHoverPrefetch();
            initializeFilters();
            applyFilters();

            if (!data.has_more) {
                break;
            }
        } catch (err) {
            console.warn("Background streaming interrupted:", err);
            break;
        }
    }

    if (indicator) indicator.style.display = "none";
}

/**
 * Initializes hover prefetching for all Category, Author, and Narrator links.
 * When the user hovers for 150ms, a prefetch request is sent to /api/search to warm the server cache.
 */
function initHoverPrefetch() {
    const links = document.querySelectorAll("a.category-link");
    links.forEach((link) => {
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
                prefetchedQueries.add(query);
                fetch(`/api/search?query=${encodeURIComponent(query)}&page=1`, { priority: "low" }).catch(() => {});
            }, 150);
        });

        link.addEventListener("mouseleave", function () {
            if (hoverTimer) {
                clearTimeout(hoverTimer);
                hoverTimer = null;
            }
        });
    });
}
