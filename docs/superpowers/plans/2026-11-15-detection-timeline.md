# Optional Detection Timeline Implementation Plan

> **For agentic workers:** Implement the plan task by task using available tools and the user-authorized execution method. Track steps with checkboxes.

**Goal:** Replace playback controls with a Timeline checkbox and a simple cumulative detection slider.

**Architecture:** Shared hook orders unique acquisition timestamps and filters points through the slider cutoff. Explorer respects current filters and selected day. Historical timeline covers selected years, area and enabled layers; switching it off restores the selected-month map.

**Tech Stack:** React, TypeScript, CSS, Playwright.

**Spec:** User's replacement timeline request and plain-slider reference, 2026-11-15. Supersedes the playback design.

## Global Constraints
Only show the slider when Timeline is checked. No play, speed, step or reset buttons. Use actual acquisition dates/times and preserve simulated provenance. Unchecking restores normal map behavior.

## Review Focus
Tied timestamps appear together; backwards scrubbing removes later detections; empty/single timestamp states; filter changes reset invalid cutoffs; count/export match displayed points; mobile layout.

### Task 1: Replace playback
**Files:** `frontend/src/MapTimeline.tsx`, `frontend/src/map-timeline.css`, `frontend/src/main.tsx`, `frontend/src/FinalWorkspace.tsx`, `scripts/verify-map-timeline.mjs`.
- [x] Implement optional timestamp slider and cumulative filtering in both views.
- [x] Browser-check exact timestamp ordering, tied records, reverse scrubbing, keyboard, toggle restoration, historical view, and mobile spacing.
- [x] Run production build, inspect diff, commit and push.

Verification: `node scripts/verify-map-timeline.mjs`, `npm run build`, and `git diff --check` passed. Browser checks include tied timestamps, reverse cumulative filtering, empty/single timestamp cases, toggle restoration in both views, keyboard, and mobile spacing. Desktop screenshot visually inspected. Corrected a global range-input margin overriding the compact slider styling.
