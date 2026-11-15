# Globe Timeline Implementation Plan

> **For agentic workers:** Implement the plan task by task using available tools and the user-authorized execution method. Track steps with checkboxes.

**Goal:** Add a styled playback scrubber to Fire explorer and Historical record globe views.

**Architecture:** Share MapTimeline presentation/playback logic, connected to existing selectedDate and historical month state. Explorer steps use selected daily analysis rows; historical steps use filtered monthly rows. Scoped CSS reserves room above the timeline for map controls.

**Tech Stack:** React, TypeScript, CSS, Playwright.

**Spec:** User's roll bar request and reference screenshot, 2026-11-15.

## Global Constraints
Use existing theme colors, floating surfaces, typography and borders. Preserve scientific provenance, missing coverage and existing filters. Do not alter map camera when scrubbing.

## Review Focus
Empty and single-step timelines; playback stops at the end and cleans up on navigation; filtering changes stop playback; disjoint selections skip excluded dates; native range keyboard/touch access; mobile map controls avoid overlap.

### Task 1: Shared timeline and integration
**Files:** Create `frontend/src/MapTimeline.tsx` and `frontend/src/map-timeline.css`; modify `frontend/src/main.tsx` and `frontend/src/FinalWorkspace.tsx`.
**Interfaces:** steps:{key:string;label:string;detail:string}[], selected:string|null, onSelect:(key:string)=>void, scopeKey:string, unit:string, optional onClear:()=>void.
- [x] Implement previous/next, play/pause, range input, speed, endpoint labels and optional reset.
- [x] Connect daily explorer selection and monthly historical selection.
- [x] Position timeline and existing map controls responsively.
- [x] Browser-check scrubbing, steps, playback/pause/end, speed, reset, selection synchronization and responsive layout; run production build and inspect diff.

Verification: `npm run build`, `git diff --check`, and `node scripts/verify-map-timeline.mjs` passed. Visually inspected desktop styling. Browser checks cover disjoint dates, native keyboard input, steps, play/pause/end, speed/reset, monthly calendar synchronization, and desktop/mobile control spacing.
