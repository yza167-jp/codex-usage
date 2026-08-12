# Changelog

## 1.4.0 — 2026-08-12

- Added native Windows 10/11 support while preserving macOS/Linux behavior.
- Added `%LOCALAPPDATA%\codex-usage\index-v2.sqlite3` as the Windows cache location.
- Fixed SQLite read-only URIs for Windows drive-letter paths and paths containing spaces.
- Normalized Windows file IDs into SQLite's signed 64-bit integer range so incremental-cache identity checks cannot overflow.
- Added automatic Windows Virtual Terminal Processing enablement for ANSI status colors.
- Added UTF-8 stdio fallback so redirected/piped output can safely contain CJK session titles and other Unicode even when Python inherits a legacy Windows code page.
- Added a `codex-usage.cmd` launcher and `install.ps1` PowerShell installer with user-PATH setup.
- Removed the default dependency on IANA `zoneinfo` data for system-local time on Windows; named `--timezone` values can use the optional `tzdata` package.
- Made exact rolling `Nh` windows elapsed-time correct across daylight-saving transitions.
- Added case-normalized path de-duplication for case-insensitive Windows filesystems.
- Added cross-platform smoke tests and GitHub Actions coverage on Windows, macOS, and Linux with Python 3.9 and 3.13.
- Validated the Windows CLI, incremental cache, CMD launcher, and PowerShell installer on GitHub-hosted Windows runners with Python 3.9 and 3.13 before release.

## 1.3.0 — 2026-08-12

- Added compact, colorized terminal summary output.
- Added live thread state (`ACTIVE`, `RECENT`, `IDLE`) and actionable health hints (`OK`, `WATCH`, `ROTATE`).
- Added trailing one-hour credit burn diagnostics.
- Added bounded agent details and longer UUID prefixes to avoid visual collisions.
- Added warm-cache hot discovery to reduce filesystem traversal on large Codex histories.
- Added incremental SQLite indexing, cache-tax attribution, main/subagent and model breakdowns, rolling-hour windows, JSON/CSV output, and performance diagnostics from earlier iterations.
