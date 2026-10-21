# Cloud capabilities, client diagnosis and observation windows

Status: v1.10.0 capability boundaries, 2026-10-21. **Release claims are per
capability: useful groups/status/export and snapshot safeguards are independent
of the still-unavailable token interface.**
No existing prices, Fast multipliers, quota calibration rules or cache histories
are changed. Historical v1.9.0/v1.9.1 documents describe those released versions;
this document describes v1.10.0.

## Initial live check (2026-10-18)

The existing `auth.json` access token and account header were reused without
refreshing or rewriting login state. The existing read-only WebSocket inventory
found 24 Cloud threads. Three existing sessions were selected; none matched an
ID in the local thread metadata index. No full transcript scan was needed.
No task was created, resumed, run or read for its conversation content.

| Interface | Observed result | Interpretation |
| --- | --- | --- |
| `/wham/usage/thread_usage/query_v2` | HTTP success, three `available` rows with discovered creation metadata; `partial` in the explicit-ID CLI follow-up | Positive lifetime weekly percentages, zero balance credits; model, reasoning effort and speed metadata are present |
| `/wham/usage/thread_usage/query` | Two batch requests, each containing the same three IDs, returned HTTP 403 | This did not individually establish that each session would fail; not zero tokens or proof of an unsupported route |
| Token fields in the successful v2 groups | Absent | No token or estimated-credit counters can be recovered from those groups |
| Selected group speeds | `standard` | Actual Fast access/accounting was not demonstrated by these samples; Fast parsing is covered by synthetic fixtures |

The denial's precise server-side cause is not known. A successful v2 response
shows the current login works for that interface; it does not establish permission
to use `/query`. The initial implementation recorded only HTTP status; refusal
origin was not classified. No response body, credentials, titles, thread IDs or
account identifiers are exposed in this verification record.
The implementation smoke check reused the same three IDs, for two rounds total
(four usage HTTP requests). The first real snapshot is recorded; no posting
increment is claimed from a single observation. No additional sessions were queried.

## Bounded official-client comparison (2026-10-21)

The stop rule was at most six active usage calls, using existing samples only.
Five were used: three direct HTTP requests and two native RPC calls. Inventory
reads and offline schema generation are separate from usage calls. No task was
created, resumed or run; no login/reset method, cookie copying, header spoofing,
client upgrade, source build or speculative backend route was used.

Offline checks found different installed clients:

- Shell CLI: `codex-cli 0.147.0`. Its generated experimental schema defines
  `account/usage/read` with null parameters, without `threadId`; it was not used
  to query account summary as a substitute for per-thread usage.
- Desktop-bundled client: `codex-cli 0.163.0-alpha.10.2`, in App version
  `26.1013.40934` (build `20770`). Its own generated schema supports `threadId`
  and a nullable `threadUsage`. This executable performed the native comparison.
- The launched clients inherited the same Codex home/config/environment. No
  custom ChatGPT backend or proxy environment variable was configured. Python
  does discover a system proxy; the native client's effective proxy routing was
  not established. Identical process environment does not prove identical
  network behavior, and this difference is not a demonstrated cause of denial.
  Sensitive executable/config paths and proxy values stay local.

| Call | Result | Meaning |
| --- | --- | --- |
| 1: v2 for one previously sampled Cloud ID, with discovered creation metadata | `available`, two model/effort/speed groups, positive weekly counter, allowance timestamp present; `comparison_plan: null` | Existing allowance/group data remains useful; comparison context is absent |
| 2: direct `/query`, that single ID | HTTP 403, `application/json`; no allowlisted error type/code, no detected challenge feature or recognized request-ID header | Batch size is not sufficient to explain this denial; no cause is established |
| 3: bundled app-server RPC, same Cloud ID | Initialize/initialized handshake succeeded; RPC result has `threadUsage: null` | No tokens or estimated credits obtained; RPC success is not usage success |
| 4: same native RPC for one Local ID with positive tokens already in the local index | `threadUsage: null` | No successful Local backend control; do not infer account-wide permission policy from null |
| 5: v2 again with identical Cloud ID and metadata | `available`; same counters, same allowance watermark, `comparison_plan: null` again | Two observations about 318 seconds apart, but allowance differences remain unknown |

The original `auth.json` bytes were unchanged after the native comparison. The
official process was stopped and collected. Native response bodies/error text
were not printed or saved. The v2 observation→snapshot→render/CSV chain was
checked on real parsed values without publishing private metadata or amounts.
Because the comparison context is null, this validates refusal to fabricate a
delta, **not live numeric weekly-difference support**. The sixth call was unused.

The reference account processor maps underlying 403/404 to `threadUsage: null`.
The installed RPC output cannot distinguish those statuses or other unavailable
conditions in that build. Stop here; tokens, server estimated credits, denial
origin and real Fast behavior remain unverified. No native production fallback
is added when it has not demonstrated additional usable data.

Official implementation references (schema/behavior references, not proof that
the installed binary equals current public source):

- [Backend client and request/response schema](https://github.com/openai/codex/blob/main/codex-rs/backend-client/src/client/thread_usage.rs)
- [Official synthetic response tests](https://github.com/openai/codex/blob/main/codex-rs/backend-client/src/client/thread_usage_tests.rs)
- [Account request processor](https://github.com/openai/codex/blob/main/codex-rs/app-server/src/request_processors/account_processor.rs)
- [App-server protocol](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/v2/thread_usage.rs)
- [Account processor reviewed on October 21](https://github.com/openai/codex/blob/a6839a481223fb5faab539a9eb2b7174ae29e560/codex-rs/app-server/src/request_processors/account_processor.rs)
- [Version-matched schema generation and connection initialization](https://learn.chatgpt.com/docs/app-server)

The referenced thread schema and account processor expose cumulative groups,
without per-turn/request usage timestamps. Inventory creation/update times are
metadata, not timestamps for token charges. No reliable dated history source
was established, so execution-time Cloud 1h/12h/24h/7d accounting is unavailable.

There is a separate [ChatGPT turn-cost query](https://github.com/openai/codex/blob/a6839a481223fb5faab539a9eb2b7174ae29e560/codex-rs/backend-client/src/client/chatgpt_turn_cost.rs)
at `/wham/usage/thread-estimates/query`: it accepts thread/turn IDs and returns
turn ID, optional model/USD estimate and settled response IDs. It is not a
token or subscription-allowance ledger. Durable applicability and historical
coverage remain future investigation; this route was not queried here. Turn
timestamps and live `thread/tokenUsage/updated` notifications do not establish
historical token replay. API-key turn costs are not a subscription substitute.

## Collection and failure isolation

Both endpoints use the existing HTTPS transport, login, timeout, redirect refusal,
inventory and 50-thread batches. `/query` sends `{"thread_ids":["..."]}`; v2 keeps
its existing request. Distinct thread IDs are queried once per endpoint/batch,
without descendant rollup. Response IDs must belong to the request and may not
repeat. There is no automatic retry. A failed endpoint is skipped for subsequent
batches of that report; available results from the other endpoint are retained.
If both fail without any usable response, the command fails explicitly.

HTTP 403 is cached for **15 minutes**, scoped by account/Codex home, endpoint,
exact request, tool/Python version, auth-file revision and resolved proxy
configuration. Only hashes of context/request identity are stored. Cache hits
expose `cached` and `cache_expires_at`; `--no-cache` bypasses them. A changed
account/client/request is independent. Missing rows, empty counters, 401, 404
and transient errors do not create a capability denial. This deliberately does
not extrapolate a thread-specific refusal into an account-wide API ban.

Safe HTTP diagnostics read at most 8 KiB into memory and retain only known
content types, allowlisted structured type/code values, a challenge-feature
boolean and recognized request-ID **presence**, never the ID or response text.
`Server: cloudflare` or `cf-ray` alone does not establish a WAF challenge.

`endpoint_errors` distinguishes `access_denied` (401/403), `unsupported`
(404/405/501), `invalid_response` and other request failures. A successful but
omitted row is `row_omitted`; a row without counters is `fields_missing`.
Neither means zero or conclusively establishes that billing has not posted yet.
Backend `data_status` is retained for the allowance interface; token availability
is independently exposed as `token_data_status`. The service can lag.
Legacy report `data_as_of` is still the oldest allowance batch timestamp, with
`data_as_of_scope=allowance_only`; `/query` does not supply token freshness.

## Metrics, grouping and missingness

| Field | Meaning |
| --- | --- |
| `input_tokens` | Cumulative input including cached input |
| `cached_input_tokens` | Cumulative cached input |
| `uncached_input_tokens` | Backend `net_new_input_tokens`, or input minus cached when both are known and consistent |
| `output_tokens` | Cumulative output; no invented reasoning-output split |
| `total_tokens` | Backend total, or input plus output when both are known |
| `estimated_usage_credits_micros` | Raw server estimate in integer millionths of a credit |
| `estimated_credits` / EST CREDITS | Server estimate divided by one million; not a local rate-card estimate |
| `estimated_usage_usd_micros`, `native_usage_usd_micros` | Optional raw backend money coordinates, preserved without converting to credits or weekly allowance |
| `token_fields_complete` | Per-field completeness across all returned token groups |

Input can also be derived from known uncached plus cached. No missing cached
field is assumed to be zero. Only nonnegative JSON integers are token/micro
counters; booleans, floating point counters and numeric strings are not silently
coerced. Integer token values stay exact beyond 2^53. Raw credit micros are
retained for exact downstream arithmetic.

Totals sum known group fields; if another group lacks that field the sum is
partial (`+?` in the terminal). All unknown fields are null in JSON and blank in
numeric CSV cells. Real zero remains zero. Empty groups do not imply zero tokens,
even when the server's credit estimate is zero. Conflicting input/cache/total
counters are retained but flagged as incomplete and excluded from snapshot
arithmetic for the affected fields.

`token_groups` retains token groups and derivation/consistency annotations;
`allowance_groups` retains the original v2 groups. Legacy `groups` combines only
exact `(model, reasoning_effort, speed)` matches, preserving v2 group fields.
Display uses existing model aliases and Standard-price ordering. Missing speed
stays Unknown; only explicit fast/priority becomes Fast. The local `--fast`
assumption does not price or change Cloud groups.

EST CREDITS, local reference CREDITS*, subscription lifetime weekly/5h amounts
and purchased/balance credits remain separate quantities. No undocumented price
or quota conversion is applied to Cloud tokens. Reasoning effort and speed are
group dimensions, not inferred billing multipliers.

## Observed server posting windows

Every explicit Cloud query with caching enabled writes minimal counters into a
separate SQLite sibling of the selected local cache (`index-v2-cloud.sqlite3`
by default). It does not open/rebuild the local index, delete history, alter
quota records or install background monitoring. `--cache-path` determines its
sibling location; `--no-cache` disables Cloud snapshot reads/writes and the
short-lived denial cache.
If account scope is unavailable or storage fails, lifetime metrics remain usable
and `snapshot_status` explains that windows were not recorded.

Stored data consists of a hash scoped by Codex home and account identity, thread
ID, UTC observation time, allowance data timestamp, data status, group counts,
complete cumulative counters and an opaque comparison-plan fingerprint.
The returned comparison context can be a string or object; its
canonical JSON is hashed once per distinct context in a report, not per thread.
No credentials, transcripts, titles, projects, raw responses or model groups
are persisted. Partial token totals do not form counter baselines.

Details default to `observed_change`, comparing only the immediately preceding
observation with the current one; an invalid interval is not bridged. One
indexed predecessor lookup supports long gaps without rescanning all history.
The four potentially identical trailing windows are not expanded in terminal
details. JSON/CSV retain `posting_windows` for 1h/12h/24h/7d; combined commands
also show/export `selected_period`. Each metric reports:

- The sum of nonnegative differences between consecutive comparable snapshots
  whose **two endpoints both lie inside the window**.
- `covered_seconds`, `uncovered_seconds`, interval count, `complete_window`,
  `discontinuity` and explicit `unavailable_reasons`.
- Null when no valid interval exists; zero only for an observed unchanged counter.

No interval is prorated across the window boundary. Missing counters and counter
decreases break continuity rather than being bridged or clamped to zero.
Allowance/balance comparisons also break on a missing/changed comparison plan
or regressing server watermark. Changes in data status or group count break the
corresponding allowance/token comparisons, including partial→available backfill.
Existing snapshots without the new metadata establish a new baseline rather
than silently inheriting comparability. Existing
observations at the same timestamp are preserved and do not double count.
Separate account scopes cannot teach one another's deltas. Earlier history is
preserved even when outside the current reporting window.

These are **nonnegative counter changes in comparable observation segments**,
not exact task execution times, not a backfill of the time before installation,
and not Local's trailing-hour burn. Even a completely covered observation window
does not remove server posting latency. A first observation only establishes a
baseline. Changing group availability, corrections and server lag can leave
gaps. For `100 → 80 → 90`, the valid final `+10` is labeled discontinuous, not a
net `+10` for the whole window. Even unchanged group counts cannot rule out
backfill: no counter growth is presented as proof of new task execution.

`snapshot_observed_at` is local observation time, while `allowance_data_as_of`
is the server allowance watermark. Each window records first/last watermarks
and whether they advanced. Token freshness stays unknown. `complete_window`
means complete **observation** coverage only; `execution_time_attribution` is
false. Two equal stale counters mean observed unchanged, not confirmed zero
consumption. No local/Cloud numeric total is constructed, including for BOTH.

## Commands and examples

```bash
codex-usage cloud --details
codex-usage 12h --cloud --details --wide
codex-usage 24h --cloud --json
codex-usage cloud --csv
```

Sanitized shape of the currently blocked token output (values omitted):

```text
Cloud query: access_denied (HTTP 403); other metrics remain separate.
Cloud models: 6.1 Sol
Cloud tiers: STD
Cloud token data: unavailable (access_denied)
Cloud observed change since previous observation:
— (0s comparable; 318s unknown; comparison context missing; allowance change unknown)
Comparison context missing; allowance/balance changes remain unknown.
```

Synthetic successful-schema example, **not a live account claim**:

```text
Cloud lifetime tokens: INPUT 100 · CACHED 20 · UNCACHED 80 · OUTPUT 40 · TOTAL 140
  6.1 Sol · effort xhigh · speed fast · I/C/O 100/20/40 · EST CREDITS 2.500001
```

PROJECT/SESSION/SRC and exact-ID display joins are unchanged. A shared root has
one detail section with two measurement scopes. Same titles never merge, and
Cloud children whose local usage was rolled into a parent stay separately
annotated. Only LOCAL TOTAL is computed. JSON's old local `sessions` and
`cloud_usage` objects remain; combined CSV still has adjacent host/scope rows
for a matching ID. New counters and JSON-encoded grouping/window columns are
additive; Cloud rows never populate the local `credit_estimate` column. New CSV
columns include `snapshot_observed_at`, `allowance_data_as_of`, `comparison_plan`
and `observed_change_json`; JSON preserves the corresponding structured data.

## Verification and release gate

Mock tests cover the official request/response format, derivation, missing and
zero values, inconsistent counters, raw micro units, integer precision, denied
and unsupported endpoints, bounded failure behavior, exact-ID joins, export
compatibility, model/tier/effort display and CJK widths from 80 through 144 cells.
Snapshot tests cover baselines, boundary exclusion, partial/full coverage,
decreases, missing data, account/plan changes, historical windows, duplicate
observations, minimal storage and opt-out. Additional regressions cover stale
watermarks, availability/group changes, missing comparison context, long gaps,
denial expiry/scope isolation, redaction and compact terminal details. Run
`python3 -m unittest discover -s tests`.

Release gates apply to the actual claims:

| Capability | Evidence / release boundary |
| --- | --- |
| Lifetime allowances, model/effort/speed, states, exports | Live v2 data plus mock regression; Standard samples only |
| Minimal snapshots, freshness/context handling, unavailable deltas | Two real observations plus regression; current sample has no comparable allowance delta |
| Valid numeric differences, corrections and window coverage | Mock-tested conditional calculation; no claim of live weekly differences on this account |
| Token / server estimated-credit parser | Conditional fallback only; live availability remains blocked |
| Precise historical Cloud windows or combined Local+Cloud totals | Not provided |

Merge/release after regression and Linux/macOS/Windows CI pass, while preserving
these limitations in the README, PR and release notes. Resolving `/query` is not
a gate for unrelated verified capabilities.
