document.addEventListener("DOMContentLoaded", function () {
  // Initialize filtering if results are present
  if (document.querySelectorAll(".result-row").length > 0) {
    populateFilters();
    document
      .getElementById("filter-button")
      .addEventListener("click", applyFilters);
    document
      .getElementById("clear-button")
      .addEventListener("click", clearFilters);
  }
});

// --- Filtering Functions ---

function populateFilters() {
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

function applyFilters() {
  const language = document.getElementById("language-filter").value;
  const bitrate = document.getElementById("bitrate-filter").value;
  const format = document.getElementById("format-filter").value;
  const maxSize = parseFloat(
    document.getElementById("file-size-filter").value
  );
  const postDate = document.getElementById("post-date-filter").value;

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

    if (!isNaN(maxSize)) {
      const fileSizeParts = row.dataset.fileSize.split(" ");
      const fileSize = parseFloat(fileSizeParts[0]);
      const fileUnit = fileSizeParts[1];
      let sizeInMb = fileSize;
      if (fileUnit === "GBs") {
        sizeInMb = fileSize * 1024;
      }
      if (sizeInMb > maxSize) {
        visible = false;
      }
    }

    if (postDate) {
      try {
        const filterDate = new Date(postDate);
        const rowDateStr = row.dataset.postDate.replace(
          /(\d{1,2})\s(\w{3})\s(\d{4})/,
          "$2 $1, $3"
        );
        const rowDate = new Date(rowDateStr);
        if (rowDate < filterDate) {
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
  document.getElementById("file-size-filter").value = "";
  document.getElementById("post-date-filter").value = "";
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