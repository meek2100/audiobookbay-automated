// File: audiobook_automated/static/js/theme.js

(function () {
    // Immediate execution to prevent FOUC (Flash of Unstyled Content)
    const savedTheme = localStorage.getItem("theme") || "crow";
    document.documentElement.setAttribute("data-theme", savedTheme);

    window.toggleTheme = function () {
        const currentTheme = document.documentElement.getAttribute("data-theme");
        const newTheme = currentTheme === "crow" ? "purple" : "crow";

        document.documentElement.setAttribute("data-theme", newTheme);
        localStorage.setItem("theme", newTheme);

        // Update button icon/text if needed (optional)
        updateThemeIcon(newTheme);
    };

    function updateThemeIcon(theme) {
        const btn = document.getElementById("theme-toggle-btn");
        if (btn) {
            // Simple text toggle for now, or could swap classes
            btn.innerText = theme === "crow" ? "🌙 Crow" : "🔮 Purple";
        }
    }

    // Run once on load to set initial button state
    document.addEventListener("DOMContentLoaded", function() {
        updateThemeIcon(savedTheme);

        // Attach listener to button (CSP safe)
        const btn = document.getElementById("theme-toggle-btn");
        if (btn) {
            btn.addEventListener("click", function(e) {
                e.preventDefault();
                toggleTheme();
            });
        }
    });
})();
