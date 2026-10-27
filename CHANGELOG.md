<!-- File: CHANGELOG.md -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Put.io Torrent Client Strategy:** Integrated Put.io cloud torrent downloader (`DL_CLIENT=putio`) with Bearer token
  authentication and customizable target folder ID (`PUTIO_FOLDER_ID`).
- **UI Customization & Theming:** Added `DEFAULT_THEME` (`purple`, `dark`, `light`, `crow`), customizable `SITE_TITLE`,
  and `SITE_LOGO`.
- **Animated Splash Screen Morph:** Added video splash screen with smooth transition that shrinks and fades into the
  top-left header logo.
- **Custom Trackers Example:** Added `examples/trackers.json` demonstrating custom tracker override formats.

### Changed

- **Responsive Design:** Optimized layout breakpoints for mobile devices (iPhone 13 mini through iPad Pro and desktops)
  ensuring stacked cards on small screens and fluid navigation.
- **CI / Workflows:** Configured `uv sync --all-extras` across GitHub Actions workflows to ensure development tools
  (`pre-commit`, `mypy`, `pytest`) are available on all runners.
- **Documentation:** Updated `README.md` and `examples/.env.example` with complete configuration options and verified
  all example file links.

### Fixed

- Fixed mobile table overflow handling in E2E tests (`overflow-x: auto` on `.table-wrapper`).
- Fixed notification toast DOM class assignment and download button data attribute fallbacks.
