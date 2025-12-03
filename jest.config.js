module.exports = {
    setupFilesAfterEnv: ["<rootDir>/jest.setup.js"],
    testEnvironment: "jsdom",
    // CRITICAL: Add the new test file here
    testMatch: ["<rootDir>/tests/js/search.test.js", "<rootDir>/tests/js/actions.test.js"],
};
