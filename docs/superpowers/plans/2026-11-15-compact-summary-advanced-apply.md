# Compact Explorer Controls Implementation Plan

> **For agentic workers:** Implement the plan task by task using available tools and the user-authorized execution method. Track steps with checkboxes.

**Goal:** Narrow the sidebar tab, fit the area metrics into less space, and apply advanced settings explicitly.

**Architecture:** Adjust scoped sidebar CSS. Encapsulate advanced filter drafts in a component, merging only advanced fields into current filters on submission.

**Tech Stack:** React, TypeScript, CSS, Playwright.

**Spec:** User's three requested changes in chat on 2026-11-15.

## Global Constraints
Preserve all summary values, selected area/dates, and existing filter drawer behavior.

## Review Focus
Check summary overflow at desktop and phone sizes; keyboard access to the tab; deferred application of every advanced field; pending edits discarded on closing; latest area/dates preserved on Apply.

### Task 1: Compact sidebar
**Files:** `frontend/src/analysis-sidebar.css`.
- [x] Narrow the tab and use compact label/value metric rows.
- [x] Check dimensions, full metric visibility, and collapse/reopen in the browser.

### Task 2: Advanced settings Apply
**Files:** Create `frontend/src/AdvancedSettings.tsx`; modify `frontend/src/main.tsx` and `frontend/src/interactions.css`.
**Interfaces:** AdvancedSettings accepts current Filters and onApply:(filters:Filters)=>void. Only sensor, platform, grid and confidence fields are merged into the current Filters.
- [x] Keep local draft controls; submit all advanced fields together through existing apply handler.
- [x] Verify pending settings do not affect shared filters, Apply updates all fields, and closing resets pending edits.
- [x] Run production build and inspect diff before committing and pushing.

Verification: `npm run build`, `git diff --check`, and `node scripts/verify-advanced-settings.mjs` passed. Updated older interaction scripts to submit explicit advanced changes.
