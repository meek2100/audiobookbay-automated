// File: jest.setup.js
const fs = require("fs");
const path = require("path");

// We need to fetch and evaluate the source script to make its global functions available to JSDOM.

// --- search.js Setup ---
const searchJsPath = path.resolve(__dirname, "audiobook_automated/static/js/search.js");
const searchJsContent = fs.readFileSync(searchJsPath, "utf8");
global.searchJsContent = searchJsContent;

// --- actions.js Setup ---
const actionsJsPath = path.resolve(__dirname, "audiobook_automated/static/js/actions.js");
const actionsJsContent = fs.readFileSync(actionsJsPath, "utf8");
global.actionsJsContent = actionsJsContent;

// --- status.js Setup (NEW) ---
const statusJsPath = path.resolve(__dirname, "audiobook_automated/static/js/status.js");
const statusJsContent = fs.readFileSync(statusJsPath, "utf8");
global.statusJsContent = statusJsContent;
// ------------------------------

// --- Global Mocks ---
global.flatpickr = jest.fn((element, options) => ({
    selectedDates: [],
    clear: jest.fn(),
    options,
}));

global.noUiSlider = {
    create: jest.fn((element, options) => ({
        get: jest.fn(() => options.start),
        reset: jest.fn(),
        options,
    })),
};
