# Click to Expand Date Picker Years Implementation Plan

> **For agentic workers:** Implement the plan task by task using available tools and the user-authorized execution method. Track steps with checkboxes.

**Goal:** Show month checkboxes only after a year is clicked.

**Architecture:** Keep DatePicker's existing button toggle and selection logic; remove hover expansion and initialize expansion as collapsed.

**Tech Stack:** React, TypeScript, Vite, Playwright.

**Spec:** User request in chat, 2026-11-15.

## Global Constraints
Preserve year and month checkbox selection and Apply/Cancel behavior.

## Review Focus
Hover must not expand or switch years. Clicking toggles expansion. Keyboard activation works. Checkboxes preserve selection independently of expansion.

### Task 1: DatePicker interaction
**Files:** Modify `frontend/src/DatePicker.tsx`.
**Interfaces:** Preserve DatePicker props and existing year button's aria-expanded state.
- [x] Initialize expanded to an empty string; remove section onMouseEnter.
- [x] Verify hover, click, keyboard toggle, and checkbox selection in a browser.
- [x] Run npm run build and review the diff before committing.

Verification: Playwright checks passed for initial collapse, inert hover, click and keyboard toggles, retained month selection, switching years, and Apply dates. `npm run build` and `git diff --check` passed.
