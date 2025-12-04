const fs = require("fs");
const path = require("path");

// We need to fetch and evaluate the source script to make its global functions available to JSDOM.

// --- search.js Setup ---
const searchJsPath = path.resolve(__dirname, "app/static/js/search.js");
const searchJsContent = fs.readFileSync(searchJsPath, "utf8");
// Expose the script content globally so the test file can evaluate it inside its setup.
global.searchJsContent = searchJsContent;

// --- actions.js Setup (NEW) ---
const actionsJsPath = path.resolve(__dirname, "app/static/js/actions.js");
const actionsJsContent = fs.readFileSync(actionsJsPath, "utf8");
global.actionsJsContent = actionsJsContent;
// ------------------------------

// --- Global Mocks ---
// Mock flatpickr instance creator.
global.flatpickr = jest.fn((element, options) => ({
    selectedDates: [],
    clear: jest.fn(),
    options,
}));

// Mock noUiSlider instance creator.
global.noUiSlider = {
    create: jest.fn((element, options) => ({
        get: jest.fn(() => options.start), // Return the start values (the whole range by default)
        reset: jest.fn(),
        options,
    })),
};
