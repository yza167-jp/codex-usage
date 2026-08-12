# Changelog

## 1.3.0 — 2026-08-12

- Added compact, colorized terminal summary output.
- Added live thread state (`ACTIVE`, `RECENT`, `IDLE`) and actionable health hints (`OK`, `WATCH`, `ROTATE`).
- Added trailing one-hour credit burn diagnostics.
- Added bounded agent details and longer UUID prefixes to avoid visual collisions.
- Added warm-cache hot discovery to reduce filesystem traversal on large Codex histories.
- Added incremental SQLite indexing, cache-tax attribution, main/subagent and model breakdowns, rolling-hour windows, JSON/CSV output, and performance diagnostics from earlier iterations.
