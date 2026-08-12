# codex-usage

[中文说明](README.zh-CN.md)

`codex-usage` is an **unofficial, local-first Codex usage profiler**. It reads Codex session transcripts on your machine and summarizes token activity and estimated credit usage by session, model, main agent, and subagent.

It is designed for a question the built-in usage views do not answer directly:

> Which Codex session is using my allowance, and why?

The tool is a single Python script with **no third-party dependencies**.

## Highlights

- Per-session usage for `today`, `yesterday`, exact dates, date ranges, or rolling windows such as `6h`, `12h`, `24h`, and any `Nh`.
- Model breakdown for GPT-5.6 Sol / Terra / Luna, GPT-5.5, GPT-5.4, and GPT-5.4 mini.
- Main-agent vs. subagent attribution, with subagents rolled into their root session by default.
- `CACHE TAX`: estimated credits attributable to cached input tokens.
- `1H BURN`: credits observed in the trailing 60 minutes for live usage diagnostics.
- `ACTIVE`, `RECENT`, `IDLE`, and `OK` / `WATCH` / `ROTATE` workflow hints.
- ANSI colors for fast terminal scanning; automatically disabled for pipes, JSON, and CSV.
- Incremental SQLite index: after the first scan, unchanged JSONL files are not re-read and append-only sessions are parsed from the tail.
- Warm-cache discovery avoids walking the entire historical session tree on every invocation.
- JSON and CSV output for downstream analysis.

## Requirements

- Python **3.9+**
- A local Codex installation that stores session transcripts under `$CODEX_HOME`
- macOS or Linux

No external Python packages are required.

## Install

Clone the repository and install the script somewhere on your `PATH`:

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

```bash
# Current calendar day
codex-usage today

# Previous calendar day
codex-usage yesterday

# Exact rolling windows
codex-usage 6h
codex-usage 12h
codex-usage 24h
codex-usage 48h

# Any rolling hour window
codex-usage 168h

# Calendar ranges
codex-usage week
codex-usage 7d
codex-usage 2026-08-10
codex-usage 2026-08-01..2026-08-10
```

`24h` and `yesterday` are intentionally different:

- `24h`: from **now minus 24 hours** to now.
- `yesterday`: the previous local calendar day, `00:00–24:00`.

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

```bash
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

```bash
codex-usage 24h --details --top-agents 5
codex-usage 24h --details --all-agents
```

Restore token columns in the summary:

```bash
codex-usage 24h --wide
```

Show each subagent as a separate top-level row instead of rolling it into the root session:

```bash
codex-usage 24h --show-subagents
```

## Colors

Color is enabled automatically when stdout is a terminal.

```bash
codex-usage 24h --color always
codex-usage 24h --color never
NO_COLOR=1 codex-usage 24h
```

JSON and CSV output never contain ANSI color codes.

## JSON / CSV

```bash
codex-usage 24h --json
codex-usage 24h --csv
codex-usage week --csv > codex-week.csv
```

## Incremental index and performance

Codex session transcripts can become large during long-running agent work. `codex-usage` therefore maintains a local SQLite index.

Default cache locations:

- macOS: `~/Library/Caches/codex-usage/index-v2.sqlite3`
- Linux: `${XDG_CACHE_HOME:-~/.cache}/codex-usage/index-v2.sqlite3`

Inspect performance:

```bash
codex-usage 24h --perf
```

Example:

```text
Perf: incremental-index | discovery=hot 0.004s | files=86 | hits=27 | cold=0 | ancestor=0 | tail=1 | skipped-old=58 | read=0.2 MiB | sync=0.006s | total=0.24s
```

Useful maintenance commands:

```bash
codex-usage --cache-info
codex-usage 24h --rebuild-cache --perf
codex-usage 24h --no-cache
codex-usage 24h --full-discovery --perf
```

The index stores only the metadata and token counters needed for statistics. It does **not** copy prompt or response bodies into the SQLite cache.

## Fast mode

If every eligible request in the selected window used Codex Fast mode, you can estimate credits with the published Fast multiplier:

```bash
codex-usage 24h --fast
```

Historical speed tier is not reliably present in the local `token_count` events, so `--fast` means **assume all eligible usage in this report used Fast mode**. Do not use it for a window that mixed Standard and Fast unless that approximation is acceptable.

## Data sources and accuracy

Codex documents local session transcripts at:

- `$CODEX_HOME/sessions` (default `~/.codex/sessions`)
- `$CODEX_HOME/archived_sessions` (default `~/.codex/archived_sessions`)

`codex-usage` parses the local cumulative `token_count` events, converts them to deltas, handles rolling time windows, and attempts to avoid double-counting inherited history in full-history subagent forks.

The embedded credit rate card is a snapshot and can become stale as Codex pricing changes. The script prints its rate-card date in the report header. For current official values, check the Codex pricing documentation.

For authoritative product views:

- `/status` shows current-session information including current token usage.
- `/usage` shows account token activity views such as daily, weekly, and cumulative usage.

This tool complements those views; it does not replace them.

## Privacy

`codex-usage` is local-only:

- It does not send session data to a server.
- It does not require an OpenAI API key.
- It does not require network access.
- Its SQLite index stores statistical metadata/token counters rather than prompt/response bodies.

However, **terminal output can contain session titles and local working-directory paths**. Those may reveal project names or usernames. Review or redact output before posting logs publicly.

The Codex transcript files themselves can contain sensitive material. Do not publish your `$CODEX_HOME/sessions` directory.

## Credit-rate snapshot

The v1.3.0 script currently embeds this Codex credit-rate snapshot (credits per 1M tokens):

| Model | Input | Cached input | Output |
|---|---:|---:|---:|
| GPT-5.6 Sol | 125 | 12.5 | 750 |
| GPT-5.6 Terra | 50 | 5 | 300 |
| GPT-5.6 Luna | 5 | 0.5 | 30 |
| GPT-5.5 | 125 | 12.5 | 750 |
| GPT-5.4 | 62.5 | 6.25 | 375 |
| GPT-5.4 mini | 18.75 | 1.875 | 113 |

The script also recognizes the current Daybreak rates included in its internal rate card.

## Limitations

- Local telemetry is not a server-side billing ledger.
- Credit estimates depend on the embedded rate card and may lag pricing changes.
- Mixed Standard/Fast history cannot currently be reconstructed reliably from token events.
- Parent/child lineage can be incomplete; unresolved children are marked as orphan subagents.
- Thread `OK` / `WATCH` / `ROTATE` labels are workflow heuristics.
- Codex may change its local transcript schema in the future.

## Development

Smoke-test the public script with:

```bash
python3 codex-usage --version
python3 codex-usage --help
python3 -m py_compile codex-usage
```

To compare the incremental index with a direct parse on your own data:

```bash
codex-usage 24h --json > /tmp/cached.json
codex-usage 24h --no-cache --json > /tmp/direct.json
```

Keep in mind that an active Codex session can append new usage between the two commands.

## Official references

- [Codex pricing and credit rate card](https://learn.chatgpt.com/docs/pricing)
- [Codex troubleshooting: local session transcript paths](https://learn.chatgpt.com/docs/reference/troubleshooting)
- [Codex developer commands: `/status` and `/usage`](https://learn.chatgpt.com/docs/developer-commands)

## Disclaimer

This project is unofficial and is not affiliated with or endorsed by OpenAI. “OpenAI”, “ChatGPT”, and “Codex” are trademarks of their respective owner.

## License

MIT. See [LICENSE](LICENSE).
