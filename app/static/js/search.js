document.addEventListener("DOMContentLoaded", function () {
  // Initialize filtering if results are present
  if (document.querySelectorAll(".result-row").length > 0) {
    initializeFilters();
    document
      .getElementById("filter-button")
      .addEventListener("click", applyFilters);
    document
      .getElementById("clear-button")
      .addEventListener("click", clearFilters);
  }
});

let datePicker;

function initializeFilters() {
    populateSelectFilters();
    // Initialize the date range picker
    datePicker = flatpickr("#date-range-filter", {
        mode: "range",
        dateFormat: "Y-m-d"
    });
}

// --- Filtering Functions ---

function populateSelectFilters() {
  const languages = new Set();
  const bitrates = new Set();
  const formats = new Set();

  document.querySelectorAll(".result-row").forEach((row) => {
    languages.add(row.dataset.language);
    bitrates.add(row.dataset.bitrate);
    formats.add(row.dataset.format);
  });

  const languageFilter = document.getElementById("language-filter");
  languages.forEach((lang) => {
    if (lang && lang !== "N/A") {
      const option = document.createElement("option");
      option.value = lang;
      option.textContent = lang;
      languageFilter.appendChild(option);
    }
  });

  const bitrateFilter = document.getElementById("bitrate-filter");
  bitrates.forEach((rate) => {
    if (rate && rate !== "N/A") {
      const option = document.createElement("option");
      option.value = rate;
      option.textContent = rate;
      bitrateFilter.appendChild(option);
    }
  });

  const formatFilter = document.getElementById("format-filter");
  formats.forEach((format) => {
    if (format && format !== "N/A") {
      const option = document.createElement("option");
      option.value = format;
      option.textContent = format;
      formatFilter.appendChild(option);
    }
  });
}

function parseFileSizeToMB(sizeString) {
    if (!sizeString || sizeString === "N/A") return null;

    const parts = sizeString.trim().split(/\s+/);
    if (parts.length < 2) return null;

    const size = parseFloat(parts[0]);
    const unit = parts[1].toUpperCase();

    if (isNaN(size)) return null;

    if (unit.startsWith("GB")) {
        return size * 1024;
    }
    if (unit.startsWith("TB")) {
        return size * 1024 * 1024;
    }
    // Assume MB if not GB or TB
    return size;
}


function applyFilters() {
  const language = document.getElementById("language-filter").value;
  const bitrate = document.getElementById("bitrate-filter").value;
  const format = document.getElementById("format-filter").value;
  const minSize = parseFloat(document.getElementById("min-size-filter").value);
  const maxSize = parseFloat(document.getElementById("max-size-filter").value);
  const selectedDates = datePicker.selectedDates;

  document.querySelectorAll(".result-row").forEach((row) => {
    let visible = true;

    if (language && row.dataset.language !== language) {
      visible = false;
    }
    if (bitrate && row.dataset.bitrate !== bitrate) {
      visible = false;
    }
    if (format && row.dataset.format !== format) {
      visible = false;
    }
    
    // File size range filtering
    const rowSizeMB = parseFileSizeToMB(row.dataset.fileSize);
    if (rowSizeMB !== null) {
        if (!isNaN(minSize) && rowSizeMB < minSize) {
            visible = false;
        }
        if (!isNaN(maxSize) && rowSizeMB > maxSize) {
            visible = false;
        }
    }

    // Date range filtering
    if (selectedDates.length === 2) {
        try {
            const startDate = selectedDates[0];
            const endDate = selectedDates[1];
            // Standardize the date format from the HTML before parsing
            const rowDateStr = row.dataset.postDate.replace(/(\d{1,2})\s(\w{3})\s(\d{4})/, '$2 $1, $3');
            const rowDate = new Date(rowDateStr);

            // Set time to 0 to compare dates only
            rowDate.setHours(0, 0, 0, 0);

            if (rowDate < startDate || rowDate > endDate) {
                visible = false;
            }
        } catch (e) {
            console.error("Invalid date format", e);
        }
    }

    row.style.display = visible ? "" : "none";
  });
}

function clearFilters() {
  document.getElementById("language-filter").value = "";
  document.getElementById("bitrate-filter").value = "";
  document.getElementById("format-filter").value = "";
  document.getElementById("min-size-filter").value = "";
  document.getElementById("max-size-filter").value = "";
  if (datePicker) {
      datePicker.clear();
  }
  
  document.querySelectorAll(".result-row").forEach((row) => {
    row.style.display = "";
  });
}

// --- Search Interaction Functions ---

function showLoadingSpinner() {
  const buttonSpinner = document.getElementById("button-spinner");
  buttonSpinner.style.display = "inline-block";
  setTimeout(showScrollingMessages, 5000);
}

function hideLoadingSpinner() {
  const buttonSpinner = document.getElementById("button-spinner");
  buttonSpinner.style.display = "none";
  hideScrollingMessages();
}

const messages = [
  "Searching... This better be worth it!",
  "Hold on, this takes a while...",
  "Still searching... Maybe grab a snack?",
  "Patience, young grasshopper...",
  "Wow, this is taking a minute!",
  "Don’t worry, I got this!",
  "Maybe go for a walk?",
  "Still thinking... Almost there!",
  "Finding the best results for you!",
  "Hang tight! Searching magic happening!",
  "One moment... while I consult the ancients.",
  "Beep boop... processing... please wait...",
  "My hamsters are running on a wheel, almost there!",
  "Just gathering some pixie dust, be right back!",
  "Is it lunchtime yet? Oh, searching... right.",
  "Please remain calm, the search is in progress.",
  "Warning: Search may cause extreme awesomeness.",
  "Calculating the optimal route to your results...",
  "Almost there... just defragmenting my brain.",
  "Searching... because the internet is a big place!",
  "Polishing the search results for your viewing pleasure.",
  "The search is strong with this one.",
  "Please wait while I summon the search demons.",
  "Searching in hyperspace... almost there!",
  "My coffee is kicking in... search commencing!",
  "Just a few more gigabytes to process...",
  "Rome wasn't built in a day.",
  "Don't blame me, the internet is slow today.",
  "Almost there... just need to find the right key...",
];
let messageIndex = 0;
let intervalId = null;

function showScrollingMessages() {
  const messageScroller = document.getElementById("message-scroller");
  const scrollingMessage = document.getElementById("scrolling-message");
  const shuffledMessages = messages.sort(() => Math.random() - 0.5);
  messageScroller.style.display = "block";
  scrollingMessage.textContent = shuffledMessages[messageIndex];
  intervalId = setInterval(() => {
    messageIndex = (messageIndex + 1) % messages.length;
    scrollingMessage.textContent = shuffledMessages[messageIndex];
  }, 5000);
}

function hideScrollingMessages() {
  const messageScroller = document.getElementById("message-scroller");
  if (intervalId) {
    clearInterval(intervalId);
    intervalId = null;
  }
  messageScroller.style.display = "none";
}

function sendToQB(link, title) {
  fetch("/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ link: link, title: title }),
  })
    .then((response) => response.json())
    .then((data) => {
      alert(data.message);
      hideLoadingSpinner();
    });
}