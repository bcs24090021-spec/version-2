# Distinct Satellite Colors Implementation Plan

> **For agentic workers:** Implement the plan task by task using available tools and the user-authorized execution method. Track steps with checkboxes.

**Goal:** Clearly distinguish MODIS and VIIRS on the globe.
**Architecture:** Preserve sensor identity in point bins, apply fixed cyan/orange sensor colors, and label them in the map legend. Grid cells with both sensors use yellow; synthetic points remain separate and purple.
**Tech Stack:** React, TypeScript, MapLibre, CSS.
**Spec:** User's sensor-color request, 2026-11-15.

## Global Constraints
Preserve counts, filtering, timeline, and simulated provenance. Keep colors consistent with existing cyan MODIS and orange VIIRS chart series.

## Review Focus
Colocated sensors remain distinguishable; grid aggregation retains total counts; mobile legends fit; simulation colors match provenance legend.

### Task 1: Sensor colors
- [x] Update point grouping, paint expressions and legends; draw larger MODIS circles underneath VIIRS.
- [x] Run sensor aggregation checks, production build and browser map/legend checks before committing.

Verification: sensor aggregation checks and production build passed. Browser checks confirmed cyan/orange labeled swatches, mixed-grid legend, mobile fit, and no detected layer expression errors. Historical legend uses the same sensor and simulation colors.
