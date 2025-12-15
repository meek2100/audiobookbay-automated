// tests/js/vendor_integration.test.js
/**
 * @jest-environment jsdom
 */

const fs = require("fs");
const path = require("path");

// Define paths to the actual vendor files
const flatpickrPath = path.resolve(__dirname, "../../audiobook_automated/static/vendor/js/flatpickr.min.js");
const noUiSliderPath = path.resolve(__dirname, "../../audiobook_automated/static/vendor/js/nouislider.min.js");

describe("Vendor Library Integration", () => {
    // Ensure the DOM is clean
    beforeEach(() => {
        document.body.innerHTML = '<div id="test-element"></div>';
        // Clean up globals if they persist
        delete window.flatpickr;
        delete window.noUiSlider;
    });

    test("flatpickr.min.js should load and expose global object", () => {
        // Read the file content
        const scriptContent = fs.readFileSync(flatpickrPath, "utf8");

        // Trick UMD into thinking we are in the browser by hiding module/exports
        // We use a self-executing function to create a scope where these are undefined
        // causing the UMD wrapper to fall back to attaching to 'window' (this)
        (function () {
            const module = undefined;
            const exports = undefined;
            const define = undefined; // Also hide AMD define if present
            eval(scriptContent);
        })();

        // Verify the global variable exists
        expect(window.flatpickr).toBeDefined();
        expect(typeof window.flatpickr).toBe("function");

        // Verify it can actually instantiate on an element
        const element = document.getElementById("test-element");
        const instance = window.flatpickr(element, {});

        // Basic check that an instance object was returned
        expect(instance).toBeDefined();
        expect(instance.element).toBe(element);
    });

    test("nouislider.min.js should load and expose global object", () => {
        // Read the file content
        const scriptContent = fs.readFileSync(noUiSliderPath, "utf8");

        // Trick UMD into thinking we are in the browser
        (function () {
            const module = undefined;
            const exports = undefined;
            const define = undefined;
            eval(scriptContent);
        })();

        // Verify the global variable exists
        expect(window.noUiSlider).toBeDefined();
        // noUiSlider usually exposes an object with a 'create' method
        expect(typeof window.noUiSlider.create).toBe("function");

        // Verify basic instantiation
        const element = document.getElementById("test-element");
        window.noUiSlider.create(element, {
            start: [20, 80],
            connect: true,
            range: {
                min: 0,
                max: 100,
            },
        });

        // Check if noUiSlider added its class to the element
        expect(element.classList.contains("noUi-target")).toBe(true);
        // Check if handles were created
        expect(element.querySelectorAll(".noUi-handle").length).toBeGreaterThan(0);
    });
});
