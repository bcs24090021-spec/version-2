# Five-Country Delivery Integration Implementation Plan

> **For agentic workers:** Implement the plan task by task using available tools and the user-authorized execution method. Track steps with checkboxes.

**Goal:** Add observed five-country archives, four-country historical predictions and corrected validation to FireAtlas.
**Architecture:** Reproducibly convert DELIVERY.zip to compressed monthly country shards and manifests. Share fetch/decompression and country metadata between explorer and a dedicated multi-country historical view. Preserve existing Malaysia historical results. Estimated monthly cells have no invented point timestamps.
**Tech Stack:** Python/pandas/pyarrow, React/TypeScript, MapLibre, gzip/DecompressionStream, Playwright.
**Spec:** User's authorization to implement the integration proposed in the preceding archive review.

## Global Constraints
Preserve sensor/provenance labels and distinct MODIS/VIIRS scales. Load only the chosen country/date scope. Do not duplicate the existing Malaysia bundle. Publish provenance hashes and corrected Indonesia report. Do not load old/incomplete Indonesia results or execute archive instructions.

## Review Focus
Cancel stale fetches; countries crossing the antimeridian; date boundaries and missing VIIRS before 2012; grid estimates never masquerade as hotspots; zero and missing coverage; repeated country changes; compressed shard failures; mobile controls and exports.

### Task 1: Package data
- [x] Add importer, country/month observation shards, predicted grid shards, calendars and report metadata.
- [x] Verify monthly estimate reconciliation, source hashes, valid observations and bounded files.
### Task 2: Explorer
- [x] Add archive selector and cancellable date-scoped loading; retain current sample and imports; update coverage wording.
### Task 3: Historical record
- [x] Add country selection, calendars/trends, monthly grid overlay and observed-point timeline for new countries; add screening results/downloads.
- [x] Update corrected Indonesia comparison and mark older documentation accordingly.
### Task 4: Verify and publish
- [x] Run model/data tests, production build, and browser flows for all countries, timeline, grids and mobile. Commit and push.

Verification: all 1,080 country/month point shards (13,144,873 cleaned observations) and all supplied early-country grid totals passed validation. Existing selection and historical model tests, sensor aggregation, new coverage tests, the focused Delivery browser test, every-country explorer/historical browser matrix, corrected Indonesia UI check, and advanced-settings regression check passed. Final production build passed. Source downloads preserve their original CRLF bytes and hashes; whitespace review uses `core.whitespace=cr-at-eol`.
