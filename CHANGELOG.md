# Changelog

All notable changes to Redd-Archiver will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Move Playwright from required dependencies to optional `screenshots` extra to fix installation errors for users who don't need screenshot capture functionality
  - Playwright is now only required when running `tools/capture_screenshots.py`
  - Install with `uv sync --extra screenshots` if screenshot capture is needed
  - Regular archive generation no longer requires Playwright or browser binaries
