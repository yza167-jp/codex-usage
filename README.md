# codex-usage

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

For older/truncated records with no persisted tier marker, the default estimate uses Standard pricing as a conservative lower bound and marks the row with `+` / `≥`. `--fast` is retained as an explicit fallback, but now resolves **only Unknown segments** as Fast; it never overrides a detected Standard or Fast setting.

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

`WEEKLY≈` is intentionally marked with `≈`: it is an attribution estimate, **not** an authoritative OpenAI billing/quota meter. When the credit total is partial because an unpriced model is present, `WEEKLY≈ ≥x%` is a **lower bound based only on the priced usage**.

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

## How `WEEKLY≈` learns

The tool keeps local quota observations in the same SQLite cache used for rollout indexing. Each observation contains only the calibration metadata it needs:

```text
hashed local account key
plan type
weekly reset timestamp
weekly used percent
local credit-equivalent usage
rate-card version
standard/fast credit mode
snapshot timestamp/source
```

Raw access/refresh/ID tokens are **not** copied into the `codex-usage` database or printed.

### First estimate

When a weekly snapshot is available, the tool reconstructs local credits from the beginning of that weekly window through the snapshot time.

If the backend says `40%` is used and local history accounts for `15,200 CREDITS*`, the initial effective conversion is:

```text
1 weekly percentage point ≈ 380 CREDITS*
effective weekly capacity ≈ 38,000 CREDITS*
confidence: LOW
```

This does **not** mean OpenAI granted 38,000 purchased credits. It is only an effective credit-equivalent scale for attributing the included weekly allowance.

### Repeated observations

As new quota snapshots appear, the tool learns from deltas inside the same weekly reset period:

```text
Δ local CREDITS* / Δ backend weekly used%
```

It uses a weighted median and rejects conspicuously low/high intervals. Low local-credit-per-percentage intervals often mean some weekly allowance moved because of activity that this machine cannot see.

Confidence progresses roughly as:

- `LEARNING` — no usable conversion yet
- `LOW` — baseline or too little observed quota movement
- `MEDIUM` — multiple clean delta intervals
- `HIGH` — several consistent intervals covering a meaningful amount of weekly movement

Calibration is segmented by account, plan, rate-card version, credit mode, and weekly reset epoch. A new plan/reset therefore does not blindly reuse an incompatible weekly observation series.

## Local coverage

`local coverage≈` compares the locally explained weekly movement with the backend-used percentage under the current calibration.

A low value can indicate activity outside the local transcript set—for example another device or another product sharing the same agentic allowance—or simply an immature calibration. It is diagnostic, not an account audit.

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
