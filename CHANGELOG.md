# Changelog

## 1.7.2 — 2026-09-06

- Split terminal PROJECT and SESSION columns using structured project metadata; preserve Codex names, fallback labels, duplicate markers and subagent identity.
- Reserve 18/33 cells for project/session at the 144-cell cap. Move --wide token diagnostics to continuation lines rather than squeezing names.
- Separate project metadata in DETAILS and add a PROJECT column to Agent breakdown; keep full model continuations and aligned numeric totals.
- Retain project fallback metadata for unnamed sessions and display their short ID instead of repeating the project as a task.
- Preserve credits, Fast attribution, weekly calibration, cache schema and existing JSON/CSV fields. No cache rebuild is needed.
- Add project/session separation and rendering regression coverage.

## 1.7.1 — 2026-09-05

- Keep full model lists visible using automatic wrapped Models continuation lines instead of ellipsizing names in narrow MODEL(S) cells.
- Use a complete first model plus an additional-model count, or a compact count when necessary; fitting model lists remain inline.
- Apply the same display policy to normal/wide summaries, agent breakdowns and long model IDs in model breakdowns.
- Preserve the 144-cell report cap, SESSION width, numeric alignment, all accounting/calibration code and JSON/CSV exports; no cache rebuild is needed.
- Add regressions for many/long/CJK model names, mixed tiers, color, narrow/fullscreen layouts, detail tables and unchanged accounting outputs.

## 1.7.0 — 2026-09-05

- Added GPT-6 Astra Work/Codex reference pricing: 250 / 25 / 1,250 credits per million input / cached input / output tokens, with a 2.5x Fast multiplier.
- Recognized the canonical `gpt-6-astra` model, exact tool shorthand aliases and narrowly matched dated Astra names; kept other GPT-6 variants unpriced rather than using a family-wide wildcard.
- Integrated GPT-6 with existing session/TOTAL/1H, component, model/tier, main/subagent, weekly, JSON and CSV accounting through the shared rate map.
- Documented Codex versus API pricing differences, including no Astra Codex cache-write or >272K long-context surcharge.
- Preserved existing model rates, complete calibration history, schema-v3 token cache, weekly-first layout and 144-cell project-aware output. Cached GPT-6 events need no rebuild to become priceable.
- Added synthetic regressions for Fast/Standard/Unknown, model switching, aliases, cache reuse, mixed-agent rollup, exports, weekly reset and calibration compatibility.

## 1.6.2 — 2026-09-01

- Rebalanced the capped 144-cell `--wide` summary so SESSION receives 34 cells instead of roughly 18.
- Packed INPUT/CACHED/OUTPUT into a compact `TOKENS I/C/O` triplet, preserving all three diagnostics with much less horizontal cost.
- Added project-aware session-cell fitting that shortens a long project tag first and reserves visible space for the Codex name/title.
- Added a narrow-terminal `--wide` fallback that emits token continuation lines instead of wrapping or crushing the SESSION label.
- Kept accounting, tier attribution, weekly calibration, cache schema, and detail-table right edges unchanged.

## 1.6.1 — 2026-08-30

- Preferred Codex's explicit user-facing thread `name` over the generated first-prompt title.
- Added project-aware session labels using `threads.project_id` and `projects.name`, with cwd/repository fallback for older state databases.
- Prefixed project context before templated titles so identical startup instructions remain distinguishable across projects.
- Added stable short-session suffixes when multiple visible rows still resolve to the same label.
- Exposed session name, underlying thread title, project ID, and project name in DETAILS, JSON, and CSV.
- Kept backward compatibility with older `state_5.sqlite` schemas; no token-cache rebuild is required.

## 1.6.0 — 2026-08-24

- Added automatic per-delta service-tier attribution from local `turn_context` and `thread_settings_applied` records.
- Normalized `priority`/`fast` to Fast and `default`/null to Standard; one session can now contain separately priced Standard and Fast segments.
- Treated an omitted `service_tier` in the full `thread_settings_applied` snapshot as Standard/default, preventing stale Fast state after Fast is switched off.
- Changed `--fast` from a global override into an Unknown-tier fallback. Detected Standard/Fast segments are never overwritten.
- Added `TIER(S)` to the summary plus service-tier, model-tier, and agent-tier breakdowns in DETAILS.
- Applied published Fast multipliers only to detected/assumed Fast segments. Unknown/Flex segments use conservative lower-bound semantics (`CREDITS* +`, `WEEKLY≈ ≥x%`).
- Added service-tier fields and tier breakdowns to JSON/CSV output.
- Bumped the token-event cache schema so `service_tier` and incremental parser state are persisted per rollout; quota history is retained.
- Revisioned weekly calibration to a tier-aware credit coordinate system and allowed legacy backend anchors to be safely replayed under the new accounting.

## 1.5.5 — 2026-08-13

- Made weekly allowance the primary user-facing usage unit: summary, TOTAL, detail metadata, component tables, MAIN/SUB, model, and agent breakdowns now put `WEEKLY≈` ahead of `CREDITS*`.
- Added `1H≈`, expressing trailing-60-minute burn directly as a share of one weekly allowance; credits remain a secondary diagnostic.
- Split current account state from attribution: the header now shows authoritative backend `CURRENT WEEK` used/left plus a local `Local this week≈` estimate.
- Defined report-table `WEEKLY≈` as the selected local usage expressed in units of one plan weekly allowance, so rolling reports remain meaningful even when they cross a weekly reset.
- Added interval calibration tables. Backend snapshots are stored even when the whole weekly window contains an unpriced model, and clean snapshot-to-snapshot intervals can teach the conversion independently.
- A dirty interval containing Spark/unknown pricing is skipped without poisoning later clean intervals in the same week.
- Rebase may use historical backend anchors from earlier reset epochs, while still re-pricing token history under the current rate card.
- Added a last-resort plan bootstrap scale (`SEED`) so authenticated Plus / Pro 5x / Pro 20x users still receive a weekly-equivalent estimate immediately after reset or on a fresh cache; observed local calibration automatically supersedes it.
- Preserved lower-bound semantics: `CREDITS* +` maps to `WEEKLY≈ ≥x%`.
- Added current-week and trailing-1h weekly-equivalent fields to JSON output.


## 1.5.2 — 2026-08-13

- Rebased legacy weekly calibration anchors onto the current token rate card instead of dividing current-rate `CREDITS*` by old-rate credits-per-percent.
- Reuses only the backend portion of a prior observation (`used_percent`, snapshot time, reset/window metadata); historical local token usage is replayed and repriced under the current rate card.
- Tries prior anchors newest-first within the same weekly reset epoch and skips any anchor whose replay contains unpriced usage such as GPT-5.3-Codex-Spark.
- Persists a successful rebase as a current-revision quota observation with source `rebased`, yielding `LOW · rebased baseline` until current-rate delta observations mature.
- Removed the raw `prior-rate fallback`: if no complete anchor can be rebased, calibration stays `LEARNING` rather than mixing incompatible credit coordinate systems.
- Added `calibration_source` to JSON and CSV subscription metadata.
- Added regression tests for rate-card rebasing, rejection of raw legacy totals, and Spark-blocked anchors.


## 1.5.1 — 2026-08-12

- Kept previously learned weekly calibration available when the current weekly window contains an unpriced model; incomplete current windows no longer force `WEEKLY≈` back to `—`.
- Displayed partial weekly attribution as a lower bound (`WEEKLY≈ ≥x%`) whenever `CREDITS*` contains priced usage plus an unpriced/unknown model.
- Corrected the embedded token rate card to the current official values for GPT-5.6 Terra (62.5 / 6.25 / 375) and GPT-5.6 Luna (25 / 2.5 / 150 credits per 1M input/cached/output tokens).
- Added official token rates for GPT-5.5 Cyber, GPT-5.3-Codex, and GPT-5.2. GPT-5.3-Codex-Spark remains intentionally unpriced because its official rate is still a research preview.
- Added an internal rate-card calibration revision so observations computed with the old v1.5.0 rates are never mixed into new delta learning. An old calibration can be shown only as `LOW · prior-rate fallback` until current-revision observations become available.
- Stopped showing `local coverage≈100%` for baseline-derived calibrations because that value is 100% by construction; local coverage is now shown only after independent delta calibration exists.
- Added JSON/CSV lower-bound metadata for partial weekly estimates.
- Added regression tests for the corrected official rates, partial `WEEKLY≈` lower bounds, and retaining a prior-rate calibration when the current window is incomplete.

## 1.5.0 — 2026-08-12

- Added subscription-aware quota attribution on top of the existing local credit estimator.
- Added local ChatGPT plan detection by reading `$CODEX_HOME/auth.json` and decoding the ID-token metadata; raw auth tokens are not copied into the `codex-usage` cache or printed.
- Added plan display mapping for `plus` → Plus, `prolite` → Pro 5x, and `pro` → Pro 20x.
- Added weekly quota discovery from recent local Codex `token_count.rate_limits` telemetry, identifying the weekly window by its duration near 10080 minutes instead of assuming `primary` or `secondary`.
- Added `Subscription` output with backend weekly used/left percentage, reset countdown, and snapshot age.
- Added `WEEKLY≈`, an estimated per-session share of the included weekly allowance.
- Added an additive `quota_observations` SQLite table; no rollout-index cache rebuild is required from v1.4.x.
- Added an initial low-confidence calibration from local weekly credits / backend weekly used percent.
- Added repeated delta calibration using local-credit changes versus backend weekly-percentage changes, a weighted median, and outlier filtering for likely unexplained/external quota movement.
- Added `LEARNING`, `LOW`, `MEDIUM`, and `HIGH` calibration confidence levels.
- Added `local coverage≈` to indicate how much backend weekly usage is approximately explained by local transcript-derived credits.
- Segmented calibration by hashed local account key, backend plan, rate-card version, standard/Fast credit mode, and weekly reset epoch.
- Added subscription/calibration fields to JSON and CSV output.
- Added `--no-quota` to disable all auth/quota discovery and weekly calibration.
- Extended `--cache-info` with the number of stored quota observations.
- Preserved the 144-cell terminal report cap, Unicode/CJK-aware layout, incremental rollout cache, and Windows/macOS/Linux support.
- Added synthetic tests for local plan decoding, weekly-window selection, repeated calibration, and quota-enabled CLI output.

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
