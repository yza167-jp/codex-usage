# codex-usage

## v1.8.0: consolidated current-window quota repair

Current reset-period evidence replaces stale historical calibration. Known-model
Unknown tiers may teach a clearly assumed **LOW** estimate; non-overlapping
blocks prevent repeated queries from inflating confidence. Partial weekly values
use `12.3%?`, not a guaranteed lower bound. Conflicts are reported rather than
silently clipped. This includes the v1.7.4 correction and all its tests.

New scoped snapshot/derived tables prevent equal-time observations from different
pools or window durations overwriting each other. Legacy raw snapshots and
observation-only anchors can be replayed without reusing old credit scalars.
**No cache rebuild:** token schema 3, original quota history and v1.7.4 derived
rows are retained. PROJECT/SESSION, model order, Fast/reference rates and JSON/CSV
fields remain compatible. See [policy and migration](docs/v1.8.0-quota-calibration.md).

## v1.7.4: repair stale weekly calibration

Current reset-period evidence now takes precedence over old calibration.
Stored snapshots are replayed into non-overlapping blocks of at least 3pp;
repeated queries on one percentage plateau do not multiply the sample count.
Unknown-tier usage can learn an explicitly assumed, LOW-confidence scale;
unpriced/Flex or incomplete-history intervals are excluded individually.

`Weekly scale` shows **current window**, **assumed tier**, or a dated historical
prior. Contradictions with the simultaneous backend percentage produce a warning,
not a hidden clamp to 100%. An explicitly labeled local-only baseline may be
used; its agreement with the backend is not independent validation.

Partial weekly estimates now display **`12.3%?`**, not `≥12.3%`: neither complete
nor partial local estimates are guaranteed quota bounds. Reference `CREDITS*`
and its `+` marker are unchanged. Earlier version notes below describe historical
behavior; this policy supersedes their calibration and weekly lower-bound claims.

**No cache rebuild.** Raw quota history and schema-3 token indexes are retained;
only derived current-window calibration is rebuilt. PROJECT/SESSION columns,
model order, Fast prices and the 144-cell report width remain unchanged.
See [policy, migration and limitations](docs/v1.7.4-current-window-calibration.md).

## v1.7.3: highest-priced model first

Model names now use a stable descending **Standard reference unit-price** order,
not first appearance, alphabetical order, or total credits spent in the session.
For example, Astra + Sol + Luna is shown as `6 Astra +2` with
`Models: 6 Astra / 5.6 Sol / 5.6 Luna`. The same order applies to inline lists,
model details, agent model lists, and JSON/CSV model lists.

Models are compared by uncached-input rate, then output and cached-input rates;
equal rates use canonical model ID order. A model's Fast usage does not promote
it above a higher-base-price model. Within the same model, details show Fast,
Standard, then unresolved Flex/Unknown. Unpriced models remain visible at the
end; no missing price is guessed. This is display order, not a capability claim.

PROJECT/SESSION widths, the 144-cell cap, session/agent row ordering, numeric
accounting, Fast multipliers, weekly calibration and cache schema are unchanged.
JSON/CSV fields and numbers remain compatible; only model-list ordering changes.
No new flag, network lookup or cache rebuild is needed.

## v1.7.2: separate PROJECT and SESSION columns

The terminal summary now has independent `PROJECT` and `SESSION` columns.
PROJECT uses the assigned Codex project or the existing cwd/repository fallback;
SESSION contains the Codex name/title without the tool-added project prefix.
At the 144-cell report cap, the columns receive 18 and 33 cells respectively.
Missing projects display `—`; unnamed sessions use a short session ID. Duplicate
session markers, subagent rollups, and v1.7.1 full model continuations are retained.

`--wide` keeps this same main row and shows `TOKENS I/C/O` on dim continuation
lines, instead of shrinking the names again. DETAILS places the full project in
its own metadata line; Agent breakdown also separates PROJECT from ROLE / SESSION.
No new flag, pricing/calibration change or cache rebuild is needed. JSON/CSV keep
their existing combined title and separate project/name fields for compatibility.

## v1.7.1: complete model lists without wider tables

When `MODEL(S)` does not fit, the main row uses a complete first model plus
the count of additional models (for example, `5.6 Sol +1`). An indented,
dim `Models: 5.6 Sol / 6 Astra` continuation then lists every model. A
fitting list stays inline, so ordinary single-model rows do not grow.
Very long model identifiers and long lists wrap within the report width
rather than losing their suffixes to an ellipsis. This applies to normal
and `--wide` summaries and to model/agent details.

The 144-cell cap, 34-cell wide SESSION column, numeric column alignment,
accounting, JSON/CSV schemas and cache schema are unchanged. The `+N` in
MODEL(S) counts additional models; it is not the incomplete-credit `+`.
No new flag, cache rebuild, fee change or quota recalibration is required.

## v1.7.0: GPT-6 Astra support

GPT-6 Astra now participates in session, TOTAL, trailing-hour, model/tier and
subagent accounting, including weekly estimates, JSON and CSV. The verified
public **Work/Codex reference rate** is **250 / 25 / 1,250 credits per 1M
uncached input / cached input / output tokens**; **Fast uses 2.5×** those rates.
The API's Fast multiplier and API-only surcharges are not used.

`gpt-6-astra` displays as `6 Astra`. Exact `gpt-6`/`gpt6` shorthands are tool
compatibility aliases, and dated `gpt-6-astra-YYYY-MM-DD` names use the Astra
family reference rate. Other variants (including Pro and unverified WM pricing)
are not silently charged as Astra. Detected Standard/Fast and `--fast`'s
Unknown-only fallback keep their existing semantics.

**No cache rebuild is needed.** Existing token events and quota history are
retained. Old model rates, calibration coordinates, weekly-first layout,
144-cell cap and readable project/session labels are unchanged. This release
adds GPT-6; it does not refresh all older model rates or turn weekly estimates
into official quota measurements. See [reference sources and compatibility
notes](docs/v1.7.0-gpt6.md).

## v1.6.2: readable project-aware wide summaries

v1.6.2 rebalances the 144-cell summary after project-aware labels made the old `--wide` SESSION column too narrow. At the canonical report width, SESSION now receives **34 cells** and INPUT/CACHED/OUTPUT are packed into one `TOKENS I/C/O` column such as `95.2M/92.7M/405K`. Long `[project] title` labels shorten the project tag first and reserve space for the actual Codex name/title, so a row no longer degrades to only `[atomic-cross-mod…]`.

On narrower terminals, `--wide` keeps the normal readable summary and places the token triplet on an indented continuation line rather than forcing the project/session label into an unusable width. The report still respects the 144-cell cap and all accounting, Fast attribution, and weekly calibration semantics are unchanged.

## v1.6.1: project-aware session labels

The `SESSION` column now prefers the explicit name shown by Codex (`threads.name`) and prefixes it with the assigned Codex project when available. If no explicit name exists, the project is combined with Codex's preview/title; older state databases fall back to the repository/cwd name. This keeps templated prompts distinguishable across projects:

```text
[steerRL] Sparse-1 S3 comparison
[knowing-to-see] Read AGENTS.md and continue the current stage
```

If two visible sessions still resolve to the exact same label, a stable short session ID is appended. DETAILS, JSON, and CSV expose the underlying session name, thread title, project ID, and project name. This update reads only `state_5.sqlite` metadata and does not require a token-cache rebuild.

## v1.6.0: automatic Fast-mode attribution

v1.6.0 reads persisted Codex service-tier settings and associates each cumulative `token_count` delta with the tier that was active for that request. `priority` and `fast` are normalized to **Fast**; `default`/null are **Standard**. A single session can therefore be split into Standard and Fast portions instead of being priced under one global assumption.

The summary adds `TIER(S)` and DETAILS adds a dedicated service-tier table. Model and agent breakdowns also show tier, so Fast subagents are visible directly:

```text
SESSION              MODEL(S)   TIER(S)  WEEKLY≈  1H≈  CREDITS*  ...
main (+6 sub)        5.6 Sol    MIXED       8.2%  1.1%    1435.0  ...

Service tier breakdown
SERVICE TIER   WEEKLY≈   CREDITS*   SESSION%
Fast              5.4%      945.0       65.9%
Standard          2.8%      490.0       34.1%
```

For older/truncated records with no persisted tier marker, the default estimate uses Standard pricing as a conservative lower bound and marks reference credits with `+` and weekly estimates with `?` (v1.7.4). `--fast` is retained as an explicit fallback, but now resolves **only Unknown segments** as Fast; it never overrides a detected Standard or Fast setting.

A persisted `thread_settings_applied` item is a full settings snapshot: when its optional `service_tier` field is absent, v1.6 treats it as Standard/default instead of carrying an earlier Fast setting forward.

The v1.6 cache schema re-indexes token events once so each event can store `service_tier`. Quota calibration is also revisioned because tier-aware credits use a different coordinate system from v1.5's global Standard/Fast assumptions.

## v1.5.5: weekly-first usage

v1.5.5 changes the product model: **weekly subscription allowance is now the primary usage unit**, while `CREDITS*` is a secondary implementation/diagnostic unit.

The top of a report separates two different ideas:

```text
Subscription  Pro 5x · CURRENT WEEK 0.0% used / 100.0% left · reset 6d23h · snapshot now
Weekly scale  1% ≈ 180.0 credits* · LOW · historical rebase
Local this week≈ ≥0.48% · CREDITS* 86.2+
```

- `CURRENT WEEK` is the latest backend quota snapshot found locally.
- `Local this week≈` estimates how much of the current weekly allowance the local transcripts explain, even when the backend display is still rounded to `0.0%`.
- Table `WEEKLY≈` means **the selected local usage expressed as a share of one plan weekly allowance**. It is therefore still meaningful for a `24h` or longer report that crosses a quota reset; it is not claiming that all selected usage belongs to the current backend epoch.
- `1H≈` applies the same scale to the trailing 60 minutes.

Default summary order is now conceptually:

```text
SESSION  MODEL(S)  TIER(S)  WEEKLY≈  1H≈  CREDITS*  CACHE TAX  SHARE  STATUS
```

Details follow the same priority: `WEEKLY≈` precedes credits in usage components, MAIN/SUB, model, and agent tables.

### Always-available weekly estimates

v1.5.5 uses a fallback ladder so authenticated users normally get a `WEEKLY≈` value whenever they query:

1. clean snapshot-to-snapshot **delta calibration** under the current rate card;
2. a current/historical current-rate baseline, including a safely **rebased** historical backend anchor;
3. a low-confidence **plan bootstrap seed** when no usable local calibration exists yet.

The bootstrap is intentionally labeled `SEED` and is replaced automatically as real local/backend observations accumulate. Current bootstrap scales are empirical starting points, not OpenAI-published quota sizes.

### Interval learning and unpriced models

Backend quota snapshots are stored independently from cumulative local credits. When the displayed weekly percentage moves, `codex-usage` measures only the local usage between suitable snapshot plateaus. A Spark/unknown-price interval is marked incomplete and excluded from learning, but a later clean interval in the same week can still calibrate normally. This avoids the old failure mode where one unpriced model made the entire weekly epoch unusable.


[中文说明](README.zh-CN.md)

`codex-usage` is an **unofficial, local-first Codex usage profiler**. It reads the Codex data already stored on your machine and answers a practical question:

> Which Codex session is using my allowance, why is it expensive, and roughly how much of my weekly subscription allowance did it consume?

The core tool is a single Python script with **no mandatory third-party dependencies**. It supports macOS, Windows 10/11, and Linux.

## v1.5.2: rate-card calibration rebase

v1.5.2 fixes a subtler calibration issue: after the embedded token rate card changes, a historical `credits / weekly %` baseline is no longer numerically comparable with newly computed `CREDITS*`.

The tool now treats a prior quota observation as a **backend anchor**, not as a reusable credit total. For an anchor in the current weekly reset epoch it reconstructs local usage from the weekly-window start through that anchor timestamp and prices those tokens again with the current rate card. A successful replay becomes `LOW · rebased baseline`.

If a newer anchor includes an unpriced model such as GPT-5.3-Codex-Spark, it is skipped and the tool tries an earlier anchor. If no complete anchor can be replayed, calibration remains `LEARNING`; v1.5.2 deliberately does not fall back to old-rate local-credit totals. This keeps `WEEKLY≈` in the same credit coordinate system as the displayed `CREDITS*`.

## v1.5.1: partial-model resilience

v1.5.1 fixes the main edge case discovered after the first real v1.5 deployment: an unpriced model such as `GPT-5.3-Codex-Spark` no longer makes the entire weekly calibration disappear.

- If a session has `543.1+ CREDITS*`, the `+` means the priced portion is known but at least one model is unpriced. If calibration exists, the weekly column now shows a lower bound such as `WEEKLY≈ ≥3.15%` instead of `—`.
- An incomplete current weekly window is **not** saved as a new calibration observation, but an existing calibration remains usable.
- The embedded token rate card is synchronized to the current official values: GPT-5.6 Terra `62.5 / 6.25 / 375`, GPT-5.6 Luna `25 / 2.5 / 150`, GPT-5.3-Codex and GPT-5.2 `43.75 / 4.375 / 350` credits per 1M input/cached/output tokens. GPT-5.3-Codex-Spark remains intentionally unpriced while its official rate is a research preview.
- Rate-card revisions are isolated for calibration. A v1.5.0 calibration may temporarily appear as `LOW · prior-rate fallback`, but it is never mixed into v1.5.1 delta learning.
- `local coverage≈` is shown only for delta-calibrated estimates; baseline-derived coverage is hidden because it would be 100% by definition.

## v1.5.0: subscription-aware estimates

v1.5.0 adds two different kinds of quota information and keeps them deliberately separate:

- **`WEEKLY`** — the latest backend-reported weekly used/remaining percentage found in local Codex rollout telemetry. This is a quota snapshot, not reconstructed from tokens.
- **`WEEKLY≈`** — an estimate of how much of that weekly allowance a local session consumed. It is learned from the relationship between locally reconstructed `CREDITS*` and repeated backend weekly-percentage observations.

Example:

```text
Codex usage — last 6h (...) — CST (UTC+08:00)
Credit mode: Standard credits (rate card 2026-08-12)
Subscription  Pro 5x · WEEKLY 43.0% used / 57.0% left · reset 3d18h · snapshot 20s
Calibration   1% weekly ≈ 397.0 credits* · MEDIUM · 4 clean / 6.0pp · local coverage≈91%

SESSION                         MODEL(S)       CREDITS*  WEEKLY≈  CACHE TAX  1H BURN  SHARE  STATUS
/goal durable ultragoal         5.6 Sol / Luna    814.1     2.05%      632.5     134.5  60.9%  ACTIVE/WATCH
another task                    5.6 Sol            203.1     0.51%      125.1     203.1  15.2%  ACTIVE/OK
```

`WEEKLY≈` is intentionally marked with `≈`: it is an attribution estimate, **not** an authoritative OpenAI billing/quota meter. When the credit total is partial because an unpriced model is present, `WEEKLY≈ x%?` marks a partial estimate; it is **not a guaranteed quota lower bound** (v1.7.4).

## Highlights

- Per-session usage for `today`, `yesterday`, exact dates, date ranges, or rolling windows such as `6h`, `12h`, `24h`, and any `Nh`.
- Tier-aware estimated credits by model, root/main agent, and subagent, including mixed Standard/Fast sessions.
- `CACHE TAX`: the estimated credit component attributable to cached input.
- `1H BURN`: credits observed in the trailing 60 minutes.
- `ACTIVE`, `RECENT`, `IDLE` plus `OK`, `WATCH`, `ROTATE` workflow hints.
- **v1.5:** local ChatGPT plan detection, backend weekly quota snapshot, adaptive `CREDITS* → WEEKLY≈` calibration, confidence level, and local-coverage estimate.
- Incremental SQLite index and warm-cache discovery for fast repeated queries.
- ANSI color output, CJK-aware terminal-cell layout, and a stable 144-cell maximum report width.
- JSON and CSV output.
- Windows PowerShell installer and CMD launcher.
- CI on Windows/macOS/Linux with Python 3.9 and 3.13.

## Requirements

- Python **3.9+**
- A local Codex installation with session transcripts under `$CODEX_HOME` / `%CODEX_HOME%`, or a directory supplied with `--codex-home`
- macOS, Windows 10/11, or Linux

No external Python packages are required for normal usage.

## Install

### macOS / Linux

```bash
git clone https://github.com/yza167-jp/codex-usage.git
cd codex-usage
mkdir -p ~/.local/bin
install -m 755 codex-usage ~/.local/bin/codex-usage
```

Make sure `~/.local/bin` is on `PATH`, then:

```bash
codex-usage --version
codex-usage 6h
```

To update an existing clone:

```bash
cd /path/to/codex-usage
git pull
install -m 755 codex-usage ~/.local/bin/codex-usage
```

### Windows PowerShell

```powershell
git clone https://github.com/yza167-jp/codex-usage.git
cd codex-usage
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

The installer defaults to:

```text
%LOCALAPPDATA%\Programs\codex-usage
```

Open a new terminal and run:

```powershell
codex-usage --version
codex-usage 6h
```

WSL should be treated as Linux: use the Linux install path and point `--codex-home` at the Codex home visible inside WSL if necessary.

## Basic usage

```bash
codex-usage 6h
codex-usage 12h
codex-usage 24h
codex-usage today
codex-usage yesterday
codex-usage week
codex-usage 168h
codex-usage 2026-08-12
codex-usage 2026-08-01..2026-08-12
```

Useful views:

```bash
codex-usage 6h --details
codex-usage 24h --wide
codex-usage 24h --show-subagents
codex-usage 24h --details --all-agents
codex-usage 24h --perf
codex-usage 24h --json
codex-usage 24h --csv
```

Disable all v1.5 subscription/quota discovery and calibration:

```bash
codex-usage 6h --no-quota
```

## How v1.5 reads the subscription state

v1.5 favors implementation simplicity for an early local tool.

### Plan type

It reads:

```text
$CODEX_HOME/auth.json
```

and decodes the local ID-token payload to obtain the ChatGPT plan type. The current display mapping is:

| Codex plan value | Displayed by `codex-usage` |
|---|---|
| `plus` | Plus |
| `prolite` | Pro 5x |
| `pro` | Pro 20x |

These are display labels used by this tool; the backend plan value is what separates calibration regimes.

### Weekly quota snapshot

Recent rollout JSONL files contain `token_count` events. Current Codex protocol allows those events to carry `rate_limits`, including:

```text
used_percent
window_minutes
resets_at
plan_type
```

`codex-usage` examines the tails of the most recently modified rollouts, chooses the newest Codex rate-limit event by event timestamp, and identifies the weekly window by a duration near **10080 minutes (7 days)**. It does **not** assume that `primary` or `secondary` is always the weekly window.

The displayed `WEEKLY 43% used / 57% left` comes from this backend snapshot. Its age is shown so stale telemetry is visible.

## How `WEEKLY≈` learns (v1.7.4)

Raw snapshots and local calibration metadata remain in the local SQLite cache;
no access/refresh/ID tokens are copied into it. A new derived table distinguishes
complete, assumed-tier and excluded intervals, and includes account/plan/mode,
quota pool, reset, policy revision and rate-card coordinates.

The tool replays current-period snapshots and cached token deltas into disjoint
`(start,end]` blocks with at least 3pp observed movement. The first qualifying
endpoint becomes the next anchor. Unknown tiers use the same explicit Standard
(or `--fast`) assumption as the report and always remain LOW. Unpriced/Flex,
unsupported providers and incomplete history are not silently normalized.

Current blocks outrank legacy priors. A current local-only baseline can be used
when blocks are insufficient; it assumes this machine explains the account
usage. Otherwise a dated <=14-day prior or visible plan SEED provides an estimate.
No fixed Pro/Plus credit-to-percent conversion is claimed. All thresholds are
heuristics; workload changes, outside usage and telemetry lag can bias results.

Conflicting local/backend numbers are compared at one snapshot timestamp. Large
overestimates trigger a warning and, only with eligible history, an explicitly
labeled reconciled baseline. There is no percentage clipping. `local coverage≈`
is no longer displayed because a fitted conversion does not establish how much
account usage originated on this device. The legacy export field remains null.

See [the full policy and migration notes](docs/v1.7.4-current-window-calibration.md)
for independent-block counts, confidence criteria, resets, saturation, assumptions,
export compatibility and the regression tests.

## Credit estimation

`CREDITS*` is reconstructed from local token counters and the embedded rate card. Cached input is a subset of input, so the estimator charges:

```text
uncached input = input - cached input
credits* = uncached input component + cached input component + output component
```

Reasoning tokens are a subset/detail of output and are not charged twice.

`codex-usage` reconstructs the active tier from persisted `turn_context` / `thread_settings_applied` settings. `priority` is treated as Fast. When no tier marker exists, Standard pricing is shown as a lower bound; `--fast` changes only those unresolved segments to a Fast assumption.

Neither `CREDITS*` nor `WEEKLY≈` is the authoritative server-side meter.

## Cache and performance

Default cache locations:

- macOS: `~/Library/Caches/codex-usage/index-v2.sqlite3`
- Windows: `%LOCALAPPDATA%\codex-usage\index-v2.sqlite3`
- Linux: `$XDG_CACHE_HOME/codex-usage/index-v2.sqlite3` or `~/.cache/codex-usage/index-v2.sqlite3`

The cache stores token-event indexes and quota calibration observations. It does not copy full prompts/responses.

After the first scan, unchanged rollout JSONL files are not re-read; active append-only files are parsed from their new tail. v1.5 may need a one-time scan of the current weekly window so it can build the first subscription calibration baseline.

Diagnostics:

```bash
codex-usage 24h --perf
codex-usage --cache-info
codex-usage 24h --full-discovery --perf
codex-usage 24h --no-cache
```

v1.6 automatically invalidates and rebuilds the token-event portion of the cache once because service tier is now stored per event. Quota observations are retained.

## Time zones

By default the tool uses the operating system's local timezone and displays both the name/abbreviation and UTC offset, for example:

```text
CST (UTC+08:00)
```

Explicit IANA zones are supported with `--timezone`, for example:

```bash
codex-usage 24h --timezone Asia/Tokyo
```

Windows does not always ship the IANA timezone database with Python. System-local time works without it; explicit IANA zones may require the optional `tzdata` package.

## Privacy / trust boundary

This tool is local-first, but **v1.5 reads `auth.json`**, which is a credential-bearing Codex file. The implementation only decodes metadata needed for plan/account segmentation and never intentionally prints or persists the raw tokens. Still, if you distribute or audit the tool, treat this code path with the same care as any software that can read your Codex home directory.

Use `--no-quota` if you do not want `codex-usage` to inspect subscription/auth metadata.

## Limitations

- Local transcripts cannot prove that all weekly usage came from this machine.
- Backend quota semantics and plan behavior can change independently of this project.
- The credit rate card embedded in a release can become stale.
- `WEEKLY≈` is most useful after several observations; the first baseline can be biased if much of the weekly usage happened elsewhere.
- At or after an exhausted included allowance, purchased/flexible credits are a separate concept; `WEEKLY≈` should not be interpreted as extra percentage beyond 100%.

## License

MIT. See [LICENSE](LICENSE).
