# Cloud token capability and observed posting windows

Status: development branch based on v1.9.1, 2026-10-18. **Do not release v1.10.0
as verified Cloud token support while the live `/query` access denial remains.**
No existing prices, Fast multipliers, quota calibration rules or cache histories
are changed. Historical v1.9.0/v1.9.1 documents describe those released versions;
this document describes the pending implementation.

## Live read-only capability check

The existing `auth.json` access token and account header were reused without
refreshing or rewriting login state. The existing read-only WebSocket inventory
found 24 Cloud threads. Three existing sessions were selected; none matched an
ID in the local thread metadata index. No full transcript scan was needed.
No task was created, resumed, run or read for its conversation content.

| Interface | Observed result | Interpretation |
| --- | --- | --- |
| `/wham/usage/thread_usage/query_v2` | HTTP success, three `available` rows with discovered creation metadata; `partial` in the explicit-ID CLI follow-up | Positive lifetime weekly percentages, zero balance credits; model, reasoning effort and speed metadata are present |
| `/wham/usage/thread_usage/query` | HTTP 403 for the same selected IDs | Access denied at this interface; not an empty usage result, not zero tokens and not proof of an unsupported route |
| Token fields in the successful v2 groups | Absent | No token or estimated-credit counters can be recovered from those groups |
| Selected group speeds | `standard` | Actual Fast access/accounting was not demonstrated by these samples; Fast parsing is covered by synthetic fixtures |

The denial's precise server-side cause is not known. A successful v2 response
shows the current login works for that interface; it does not establish permission
to use `/query`. The implementation reports HTTP status without exposing the
response body, credentials, titles, thread IDs or account identifiers in this
verification record. No speculative endpoint probing is used to bypass denial.
The implementation smoke check reused the same three IDs, for two rounds total
(four usage HTTP requests). The first real snapshot is recorded; no posting
increment is claimed from a single observation. No additional sessions were queried.

Official implementation references:

- [Backend client and request/response schema](https://github.com/openai/codex/blob/main/codex-rs/backend-client/src/client/thread_usage.rs)
- [Official synthetic response tests](https://github.com/openai/codex/blob/main/codex-rs/backend-client/src/client/thread_usage_tests.rs)
- [Account request processor](https://github.com/openai/codex/blob/main/codex-rs/app-server/src/request_processors/account_processor.rs)
- [App-server protocol](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/v2/thread_usage.rs)

The referenced thread schema and account processor expose cumulative groups,
without per-turn/request usage timestamps. Inventory creation/update times are
metadata, not timestamps for token charges. No reliable dated history source
was established, so execution-time Cloud 1h/12h/24h/7d accounting is unavailable.

## Collection and failure isolation

Both endpoints use the existing HTTPS transport, login, timeout, redirect refusal,
inventory and 50-thread batches. `/query` sends `{"thread_ids":["..."]}`; v2 keeps
its existing request. Distinct thread IDs are queried once per endpoint/batch,
without descendant rollup. Response IDs must belong to the request and may not
repeat. There is no automatic retry. A failed endpoint is skipped for subsequent
batches of that report; available results from the other endpoint are retained.
If both fail without any usable response, the command fails explicitly.

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
sibling location; `--no-cache` disables Cloud snapshot reads and writes too.
If account scope is unavailable or storage fails, lifetime metrics remain usable
and `snapshot_status` explains that windows were not recorded.

Stored data consists of a hash scoped by Codex home and account identity, thread
ID, UTC observation time, complete cumulative counters and an opaque comparison-plan
fingerprint. The returned comparison context can be a string or object; its
canonical JSON is hashed once per distinct context in a report, not per thread.
No credentials, transcripts, titles, projects, raw responses or model groups
are persisted. Partial token totals do not form counter baselines.

On a later manual query, `posting_windows` includes 1h/12h/24h/7d; a combined
local/Cloud command also includes `selected_period`. Each metric reports:

- The sum of nonnegative differences between consecutive comparable snapshots
  whose **two endpoints both lie inside the window**.
- Coverage seconds and interval count, plus `complete_window` and `discontinuity`.
- Null when no valid interval exists; zero only for an observed unchanged counter.

No interval is prorated across the window boundary. Missing counters and counter
decreases break continuity rather than being bridged or clamped to zero.
Allowance/balance comparisons also break on a missing or changed comparison plan. Existing
observations at the same timestamp are preserved and do not double count.
Separate account scopes cannot teach one another's deltas. Earlier history is
preserved even when outside the current reporting window.

These are **server statistics posting increments observed between queries**,
not exact task execution times, not a backfill of the time before installation,
and not Local's trailing-hour burn. Even a completely covered observation window
does not remove server posting latency. A first observation only establishes a
baseline. Changing group availability, corrections and server lag can leave
gaps. No local/Cloud numeric total is constructed, including for a BOTH row.

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
Cloud lifetime tokens: INPUT — · CACHED — · UNCACHED — · OUTPUT — · TOTAL —
EST CREDITS — · token data: unavailable (access_denied)
Cloud posting delta 1h: — (need two comparable observations inside this window)
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
additive; Cloud rows never populate the local `credit_estimate` column.

## Verification and release gate

Mock tests cover the official request/response format, derivation, missing and
zero values, inconsistent counters, raw micro units, integer precision, denied
and unsupported endpoints, bounded failure behavior, exact-ID joins, export
compatibility, model/tier/effort display and CJK widths from 80 through 144 cells.
Snapshot tests cover baselines, boundary exclusion, partial/full coverage,
decreases, missing data, account/plan changes, historical windows, duplicate
observations, minimal storage and opt-out. Run `python3 -m unittest discover -s tests`.

The release gate is live confirmation of `/query` tokens and server credit
fields on an authorized existing session, followed by cross-platform CI. HTTP
403 currently prevents that confirmation. Keep the version unchanged and this
work reviewable in a PR; do not turn mock support into a v1.10.0 availability claim.
