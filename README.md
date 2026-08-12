# codex-usage

[中文说明](README.zh-CN.md)

`codex-usage` is an **unofficial, local-first Codex usage profiler**. It reads Codex session transcripts on your machine and summarizes token activity and estimated credit usage by session, model, main agent, and subagent.

It is designed for a question the built-in usage views do not answer directly:

> Which Codex session is using my allowance, and why?

The core tool is a single Python script with **no mandatory third-party dependencies**. **v1.4.0 adds native Windows support** alongside macOS and Linux.

**v1.4.1** is a terminal-UX polish release: health-aware session colors, adaptive column widths, compact detail headers, and unambiguous timezone labels.

**v1.4.2** fixes Unicode terminal-cell width handling so CJK and mixed-language session titles stay aligned instead of pushing numeric columns onto a new line. It remains dependency-free.

**v1.4.3** caps wide-terminal output to a stable readable report column and aligns the rightmost `SESSION%` edge across detailed breakdown tables.

## Highlights

- Per-session usage for `today`, `yesterday`, exact dates, date ranges, or rolling windows such as `6h`, `12h`, `24h`, and any `Nh`.
- Model breakdown for GPT-5.6 Sol / Terra / Luna, GPT-5.5, GPT-5.4, and GPT-5.4 mini.
- Main-agent vs. subagent attribution, with subagents rolled into their root session by default.
- `CACHE TAX`: estimated credits attributable to cached input tokens.
- `1H BURN`: credits observed in the trailing 60 minutes for live usage diagnostics.
- `ACTIVE`, `RECENT`, `IDLE`, and `OK` / `WATCH` / `ROTATE` workflow hints.
- ANSI colors for fast terminal scanning, including automatic VT enablement on supported Windows consoles.
- Incremental SQLite index: after the first scan, unchanged JSONL files are not re-read and append-only sessions are parsed from the tail.
- Warm-cache discovery avoids walking the entire historical session tree on every invocation.
- JSON and CSV output for downstream analysis.
- Windows PowerShell installer and CMD launcher.
- Cross-platform CI on Windows, macOS, and Linux.

## Requirements

- Python **3.9+**
- A local Codex installation that stores session transcripts under `$CODEX_HOME` / `%CODEX_HOME%`, or a path supplied with `--codex-home`
- Windows 10/11, macOS, or Linux

No external Python packages are required for normal local-time usage.

### Windows time-zone note

Python on Windows does not normally ship an IANA time-zone database. You do **not** need one for the default system-local time zone. If you explicitly use a named IANA zone such as:

```powershell
codex-usage 24h --timezone Asia/Tokyo
```

and Python reports that the zone is unavailable, install the optional `tzdata` package:

```powershell
py -3 -m pip install tzdata
```

## Install

### Windows (PowerShell)

Clone the repository and run the included installer:

```powershell
git clone https://github.com/yza167-jp/codex-usage.git
cd codex-usage
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

The installer copies `codex-usage` and `codex-usage.cmd` to:

```text
%LOCALAPPDATA%\Programs\codex-usage
```

and adds that directory to your **user PATH**. Open a new terminal and verify:

```powershell
codex-usage --version
```

You can choose another install directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -InstallDir C:\Tools\codex-usage
```

Or run without installing:

```powershell
py -3 .\codex-usage 24h
```

### macOS / Linux

```bash
git clone https://github.com/yza167-jp/codex-usage.git
cd codex-usage
mkdir -p ~/.local/bin
install -m 755 codex-usage ~/.local/bin/codex-usage
```

Make sure `~/.local/bin` is on your `PATH`. For zsh:

```bash
grep -q '.local/bin' ~/.zshrc 2>/dev/null || \
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Verify:

```bash
codex-usage --version
```

## Quick start

```text
codex-usage today
codex-usage yesterday
codex-usage 6h
codex-usage 12h
codex-usage 24h
codex-usage 48h
codex-usage 168h
codex-usage week
codex-usage 7d
codex-usage 2026-08-10
codex-usage 2026-08-01..2026-08-10
```

`24h` and `yesterday` are intentionally different:

- `24h`: the exact trailing 24-hour interval ending now.
- `yesterday`: the previous local calendar day, `00:00–24:00`.

Rolling `Nh` windows are calculated as elapsed time, including across daylight-saving transitions.

## Reading the summary

A typical summary looks like this:

```text
SESSION                        MODEL(S)            CREDITS*  CACHE TAX  1H BURN  SHARE  STATUS
current-feature-work (+4 sub)  5.6 Sol / 5.6 Luna    812.4      501.7     184.2   28.6%  ACTIVE/WATCH
older-long-session             5.6 Sol              2034.8     1510.3         —   71.4%  IDLE
```

### `CREDITS*`

An estimate reconstructed from local token counters and the embedded Codex credit rate card. It is useful for **relative attribution**—for example, comparing sessions and models—but it is **not the authoritative server-side quota meter**.

### `CACHE TAX`

The estimated credit component caused by cached input tokens. A large cache tax is often a sign that a long-lived main thread is repeatedly carrying a large context.

### `1H BURN`

Credits observed in the trailing 60 minutes. This is a rolling activity metric, not a plan limit or billing forecast.

### `STATUS`

For live windows the tool separates activity state from a workflow heuristic:

- `ACTIVE`: token activity within the last 15 minutes.
- `RECENT`: activity within the last hour.
- `IDLE`: no recent activity.
- `OK`: no strong long-context warning.
- `WATCH`: context cost is becoming worth monitoring.
- `ROTATE`: consider checkpointing project state and starting a fresh root session at a natural milestone.

These are local heuristics, not OpenAI product warnings.

## Detailed diagnostics

```text
codex-usage 24h --details
```

Adds:

- credit components: cached input / uncached input / output
- main vs. subagents
- model breakdown
- per-agent breakdown
- last activity time
- trailing one-hour burn and a simple two-hour linear projection for active threads

By default only the top eight agents are shown per session:

```text
codex-usage 24h --details --top-agents 5
codex-usage 24h --details --all-agents
```

Restore token columns in the summary:

```text
codex-usage 24h --wide
```

Show each subagent as a separate top-level row instead of rolling it into the root session:

```text
codex-usage 24h --show-subagents
```

## Colors

Color is enabled automatically when stdout is an interactive terminal. On Windows, v1.4.0 attempts to enable Virtual Terminal Processing for the current console, so Windows Terminal, modern PowerShell, and supported `cmd.exe` consoles can render the same status colors as macOS/Linux.

```text
codex-usage 24h --color always
codex-usage 24h --color never
```

The standard `NO_COLOR` environment variable is respected. JSON and CSV output never contain ANSI color codes.

## JSON / CSV

```text
codex-usage 24h --json
codex-usage 24h --csv
codex-usage week --csv > codex-week.csv
```

## Incremental index and performance

Codex session transcripts can become large during long-running agent work. `codex-usage` therefore maintains a local SQLite index.

Default cache locations:

- Windows: `%LOCALAPPDATA%\codex-usage\index-v2.sqlite3`
- macOS: `~/Library/Caches/codex-usage/index-v2.sqlite3`
- Linux: `${XDG_CACHE_HOME:-~/.cache}/codex-usage/index-v2.sqlite3`

Inspect performance:

```text
codex-usage 24h --perf
```

Example:

```text
Perf: incremental-index | discovery=hot 0.004s | files=86 | hits=27 | cold=0 | ancestor=0 | tail=1 | skipped-old=58 | read=0.2 MiB | sync=0.006s | total=0.24s
```

Useful maintenance commands:

```text
codex-usage --cache-info
codex-usage 24h --rebuild-cache --perf
codex-usage 24h --no-cache
codex-usage 24h --full-discovery --perf
```

The index stores only the metadata and token counters needed for statistics. It does **not** copy prompt or response bodies into the SQLite cache.

## Codex data location

The default is:

```text
~/.codex
```

which maps to the user's home directory on Windows, macOS, and Linux. Override it with either the `CODEX_HOME` environment variable or:

```text
codex-usage 24h --codex-home <path>
```

If your Codex sessions live inside **WSL**, the simplest and most reliable option is to run `codex-usage` inside the same WSL distribution. A native Windows invocation can still use `--codex-home` for a Windows-accessible transcript path, but the persistent profiler cache should remain on a local Windows filesystem for best SQLite performance.

## Fast mode

If every eligible request in the selected window used Codex Fast mode, you can estimate credits with the published Fast multiplier:

```text
codex-usage 24h --fast
```

Historical speed tier is not reliably present in the local `token_count` events, so `--fast` means **assume all eligible usage in this report used Fast mode**. Do not use it for a window that mixed Standard and Fast unless that approximation is acceptable.

## Data sources and accuracy

The tool reads local Codex rollout JSONL and, when present, `state_5.sqlite` for thread metadata. Token counters are converted into estimated credits using the rate card embedded in the script.

Important limitations:

- Local transcripts are telemetry, not the authoritative server-side quota meter.
- Historical Fast/Standard service tier is not reliably recoverable from token-count events.
- Model/rate-card changes can make older embedded rates stale; check the `RATE_CARD_AS_OF` value in the script.
- Full-history forks/subagents can copy inherited token counters. The tool uses parent lineage and cumulative-counter de-duplication to avoid counting inherited history twice when the needed lineage is available.
- An unresolved child can appear as `[ORPHAN SUB]` rather than being guessed into a parent session.

## Privacy

`codex-usage` is local-first:

- It does not upload your Codex transcripts.
- It does not require an API key.
- Its SQLite cache stores usage metadata and counters, not prompt/response bodies.
- Terminal output can contain local thread titles and project directory names. Review output before posting screenshots or logs publicly.

The repository contains no user-specific paths or session data.

## Cross-platform testing

The repository includes smoke tests for:

- CLI version/help
- synthetic rollout parsing with and without the incremental cache
- SQLite read-only URI handling, including paths containing spaces
- platform-specific default cache paths

GitHub Actions runs the suite on `windows-latest`, `macos-latest`, and `ubuntu-latest` with Python 3.9 and 3.13.

Run locally:

```text
python -m unittest discover -s tests -v
```

## License

MIT. See [LICENSE](LICENSE).

## Disclaimer

This project is not affiliated with or endorsed by OpenAI. Codex behavior, transcript formats, models, and rate cards may change. Treat the tool as a local diagnostic aid, not as a billing or quota authority.
