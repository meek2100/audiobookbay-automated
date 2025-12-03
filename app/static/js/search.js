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

// Global variables defined in the file
let datePicker;
let fileSizeSlider;
let messageIndex = 0;
let intervalId = null;

document.addEventListener("DOMContentLoaded", function () {
    // Initialize filtering if results are present
    if (document.querySelectorAll(".result-row").length > 0) {
        initializeFilters();
        document.getElementById("filter-button").addEventListener("click", applyFilters);
        document.getElementById("clear-button").addEventListener("click", clearFilters);
    }
});

// ROBUSTNESS: Handle Browser Back/Forward Cache (BFCache)
// If the user searches, navigates away, and clicks "Back", the page might load
// from cache with the spinner still active. This forces a reset.
window.addEventListener("pageshow", function (event) {
    if (event.persisted) {
        hideLoadingSpinner();
    }
});

// --- Helper Functions ---
function initializeFilters() {
    populateSelectFilters();
    initializeFileSizeSlider();
    initializeDateRangePicker();
}

function parseFileSizeToMB(sizeString) {
    if (!sizeString || sizeString.trim().toLowerCase() === "n/a") return null;

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

function formatFileSize(mb) {
    if (mb === null || isNaN(mb)) return "N/A";
    if (mb >= 1024 * 1024) {
        return (mb / (1024 * 1024)).toFixed(2) + " TB";
    }
    if (mb >= 1024) {
        return (mb / 1024).toFixed(2) + " GB";
    }
    return mb.toFixed(2) + " MB";
}

function initializeDateRangePicker() {
    const allDates = Array.from(document.querySelectorAll(".result-row"))
        .map((row) => {
            const dateStr = row.dataset.postDate;
            if (!dateStr || dateStr === "N/A") return null;
            try {
                let date;
                if (/^\d{1,2}\s[a-zA-Z]{3}\s\d{4}$/.test(dateStr)) {
                    const formattedStr = dateStr.replace(/(\d{1,2})\s(\w{3})\s(\d{4})/, "$2 $1, $3");
                    date = new Date(formattedStr);
                } else {
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

function populateSelectFilters() {
    const categories = new Set();
    const languages = new Set();
    const bitrates = new Set();
    const formats = new Set();

    document.querySelectorAll(".result-row").forEach((row) => {
        // --- START CATEGORY FIX: Split categories for filtering by single keyword ---
        const categoryString = row.dataset.category;
        categoryString.split(/\s+/).forEach((term) => {
            if (term && term !== "N/A" && term !== "None") {
                categories.add(term);
            }
        });
        // --- END CATEGORY FIX ---

        languages.add(row.dataset.language);
        bitrates.add(row.dataset.bitrate);
        formats.add(row.dataset.format);
    });

    const appendOptions = (id, set) => {
        const select = document.getElementById(id);
        while (select.options.length > 1) {
            select.remove(1);
        }

        const sortedValues = Array.from(set).sort((a, b) =>
            a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" })
        );

        sortedValues.forEach((val) => {
            if (val && val !== "N/A" && val !== "None") {
                const option = document.createElement("option");
                option.value = val;
                option.textContent = val;
                select.appendChild(option);
            }
        });
    };

    appendOptions("category-filter", categories);
    appendOptions("language-filter", languages);
    appendOptions("bitrate-filter", bitrates);
    appendOptions("format-filter", formats);
}

function applyFilters() {
    const category = document.getElementById("category-filter").value;
    const language = document.getElementById("language-filter").value;
    const bitrate = document.getElementById("bitrate-filter").value;
    const format = document.getElementById("format-filter").value;
    const selectedDates = datePicker ? datePicker.selectedDates : [];
    const sizeRange = fileSizeSlider ? fileSizeSlider.get().map(parseFloat) : null;

    document.querySelectorAll(".result-row").forEach((row) => {
        let visible = true;

        // --- START CATEGORY FIX: Whole Word Regex Match ---
        if (category) {
            // Check for whole word match: \b ensures boundary (e.g., matches "Fiction" but not "Non-Fiction")
            const regex = new RegExp(`\\b${category}\\b`);
            if (!regex.test(row.dataset.category)) {
                visible = false;
            }
        }
        // --- END CATEGORY FIX ---

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
            if (!rowDateStr || rowDateStr === "N/A") {
                visible = false;
            } else {
                try {
                    let rowDate;
                    if (/^\d{1,2}\s[a-zA-Z]{3}\s\d{4}$/.test(rowDateStr)) {
                        const formattedStr = rowDateStr.replace(/(\d{1,2})\s(\w{3})\s(\d{4})/, "$2 $1, $3");
                        rowDate = new Date(formattedStr);
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

function showLoadingSpinner() {
    const button = document.querySelector(".search-button");
    if (button) {
        button.disabled = true;
        if (!button.dataset.originalText) {
            button.dataset.originalText = button.querySelector(".button-text").innerText;
        }
        button.querySelector(".button-text").innerText = "Searching...";
    }

    const buttonSpinner = document.getElementById("button-spinner");
    if (buttonSpinner) buttonSpinner.style.display = "inline-block";

    setTimeout(showScrollingMessages, 3000);
}

function hideLoadingSpinner() {
    const button = document.querySelector(".search-button");
    if (button) {
        button.disabled = false;
        if (button.dataset.originalText) {
            button.querySelector(".button-text").innerText = button.dataset.originalText;
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
