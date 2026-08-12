# Changelog

## 1.4.3 — 2026-08-12

- Capped wide-terminal rendering to a stable 144-cell report column, matching the canonical `...ROTATE warnings.` status note.
- Kept the right side intentionally blank on very wide/full-screen terminals instead of stretching session titles indefinitely.
- Aligned the rightmost `SESSION%` edge across credit components, main/subagent, model, and agent detail tables.
- Extended detail separators to the same report boundary for a consistent visual frame.
- No changes to credit estimation, session attribution, rate cards, or the incremental-cache schema.

## 1.4.2 — 2026-08-12

- Fixed CJK / East Asian wide-character alignment in summary and detail tables by measuring terminal cells instead of Python string length.
- Made Unicode-aware truncation and padding shared by summary rows, detail tables, agent breakdowns, and detail headings.
- Added regression tests for CJK, mixed Chinese/ASCII text, combining marks, truncation, and left/right padding.
- Added an explicit regression for the original failure mode: a mixed CJK/ASCII session cell must pad to the exact requested terminal width without shifting later columns.
- Kept the implementation dependency-free using Python's standard `unicodedata` module.
- No changes to credit estimation, session attribution, rate cards, or the incremental-cache schema.

## 1.4.1 — 2026-08-12

- Refined terminal colors so session titles follow health first: `OK` green, `WATCH` yellow, `ROTATE` red, with inactive rows dimmed.
- Made summary column widths adapt to the current terminal width instead of using fixed widths.
- Shortened detail section headings so long goal prompts no longer dominate the screen.
- Compacted detail metadata for state, health, last activity, and trailing burn.
- Changed `rolled-up subagents` to the more precise `subagents in window`.
- Made timezone labels unambiguous by showing both the local abbreviation/name and UTC offset.

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
