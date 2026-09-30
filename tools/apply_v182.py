from pathlib import Path

root = Path('.')
p = root / 'codex-usage'
s = p.read_text(encoding='utf-8')

def replace(old, new):
    global s
    if s.count(old) != 1:
        raise RuntimeError('Expected exactly one source anchor: ' + old[:100])
    s = s.replace(old, new, 1)

replace('VERSION = "1.8.1"', 'VERSION = "1.8.2"')
replace('GPT6_RATE_CARD_AS_OF = "2026-09-27"', 'GPT6_RATE_CARD_AS_OF = "2026-09-30"')
replace('# deltas on each query, so formerly unpriced Sol/Luna blocks are re-evaluated;', '# deltas on each query, so newly supported model blocks are re-evaluated;')
replace('# about current purchased-credit promotions. GPT-6 Work/Codex reference rates\n# (checked 2026-09-27) include distinct Astra, Sol and Luna entries; see\n# docs/v1.8.1-gpt6-sol-luna.md. They are not fixed Plus/Pro quota conversions.', '# about current purchased-credit promotions. GPT-6.1 Sol Standard reference\n# rates were checked 2026-09-30; previously supported rates remain unchanged.\n# See docs/v1.8.2-gpt61-sol.md for allowance vs purchased-credit Fast semantics.\n# These are reference coordinates, not fixed Plus/Pro quota conversions.')
replace('    "gpt-6-sol": (50.0, 5.0, 250.0),', '    "gpt-6.1-sol": (50.0, 2.5, 250.0),\n    "gpt-6-sol": (50.0, 5.0, 250.0),')
replace('# Fast mode multipliers published by OpenAI.', '# Subscription-oriented reference multipliers; keep the existing scale.\n# For GPT-6-family models the current included-allowance Fast multiplier is\n# 2.5x, whereas purchased-credit Fast billing is 2x (checked 2026-09-30).\n# This map is NOT a purchased-credit invoice calculator.')
replace('    "gpt-6-astra": 2.5,  # Work/Codex, not the API Fast rate', '    "gpt-6-astra": 2.5,  # included-allowance reference, not purchased credits\n    "gpt-6.1-sol": 2.5,')
replace('    dated = re.fullmatch(r"(gpt-6-(?:astra|sol|luna))-\\d{4}-\\d{2}-\\d{2}", s)', '    dated = re.fullmatch(r"(gpt-6-(?:astra|sol|luna)|gpt-6\\.1-sol)-\\d{4}-\\d{2}-\\d{2}", s)')
replace('        "gpt-6-sol": "6 Sol",', '        "gpt-6.1-sol": "6.1 Sol",\n        "gpt-6-sol": "6 Sol",')
replace('def service_tier_display(tier: str, compact: bool = False) -> str:', '''def fast_reference_notes(buckets: Dict[str, Bucket], assume_fast_unknown: bool) -> List[str]:
    """Explain the reference basis when the new model contributes Fast usage."""
    for bucket in buckets.values():
        for key in bucket.usage_by_model:
            model, tier = split_usage_key(key)
            if model == "gpt-6.1-sol" and (
                tier == SERVICE_TIER_FAST
                or (assume_fast_unknown and tier == SERVICE_TIER_UNKNOWN)
            ):
                return [
                    "Pricing note  6.1 Sol Fast uses the 2.5x included-allowance reference; "
                    "purchased-credit Fast is 2x. CREDITS* is not a bill."
                ]
    return []


def service_tier_display(tier: str, compact: bool = False) -> str:''')
replace('    for note in unpriced_model_notes(buckets):', '''    for note in fast_reference_notes(buckets, fast):
        lines.extend(color.wrap(part, color.DIM)
                     for part in wrap_display_words(note, terminal_width))
    for note in unpriced_model_notes(buckets):''')
p.write_text(s, encoding='utf-8')
p = root / 'tests/test_codex_usage.py'
s = p.read_text(encoding='utf-8').replace('self.assertIn("1.8.1", proc.stdout)', 'self.assertIn("1.8.2", proc.stdout)')
p.write_text(s, encoding='utf-8')

updates = {
    'README.md': '''## v1.8.2: GPT-6.1 Sol

Add distinct `gpt-6.1-sol` support, displayed as **6.1 Sol**. Standard reference
credits per million uncached-input / cached-input / output tokens are
**50 / 2.5 / 250**. Cached input is half GPT-6 Sol's rate; the models are not aliases.

Fast/priority uses the existing **2.5x included-allowance reference scale**.
The current official rate card separately sets purchased-credit Fast at **2x**;
`CREDITS*` is a diagnostic reference coordinate, not that invoice. A terminal
note explains this when GPT-6.1 Sol Fast is used. See [sources and semantics](docs/v1.8.2-gpt61-sol.md).

**No cache rebuild.** Existing GPT-6.1 Sol tokens become priceable immediately,
and current quota blocks are re-evaluated from stored snapshots and deltas.
All prior prices, calibration history, model price order, exports and the
144-cell PROJECT/SESSION layout remain compatible. Unsupported suffixes,
including Ultrafast, are not silently priced as the base model.

''',
    'README.zh-CN.md': '''## v1.8.2：支持 GPT-6.1 Sol

新增独立的 `gpt-6.1-sol`，显示为 **6.1 Sol**。每百万未缓存输入／缓存输入／
输出 tokens 的 Standard 参考 credits 为 **50 / 2.5 / 250**。缓存输入单价
是 GPT-6 Sol 的一半，不能把两个型号当成别名或把整个任务费用直接减半。

Fast/priority 沿用工具的 **2.5 倍订阅内额度参考口径**；官方当前对购买 credits
另列 **2 倍** Fast 费率。`CREDITS*` 是用于估算的参考量，不是购买 credits 的
账单。涉及 GPT-6.1 Sol Fast 时终端会提示这个区别，详见[来源与语义](docs/v1.8.2-gpt61-sol.md)。

**无需重建或删除 cache。** 已缓存的新模型 tokens 会直接恢复计价，当前校准
区间由原始快照及 token 增量重新评估。旧模型费率、校准历史、价格排序、导出
和 144 格 PROJECT/SESSION 布局保留。Ultrafast、Pro、WM 等未核实后缀不会被
静默并入普通 Sol。本次仅新增模型，weekly 仍需实际观测校准。

''',
    'CHANGELOG.md': '''## 1.8.2 — 2026-09-30

- Add independent GPT-6.1 Sol Standard reference rates (50 / 2.5 / 250 credits per 1M uncached/cached/output tokens) and the `6.1 Sol` display label.
- Recognize canonical and strictly dated IDs; do not alias GPT-6 Sol, Astra, generic 6.1 or unverified Ultrafast/Pro/WM variants.
- Apply the 2.5x included-allowance Fast reference multiplier per segment. Document the distinct current 2x purchased-credit Fast rate and show a note for GPT-6.1 Sol Fast; CREDITS* is not a bill.
- Reprice existing cached events and replay formerly excluded current quota blocks without rebuilding token indexes or deleting quota history.
- Preserve all previously supported reference prices, calibration policy/keys, price-descending model order, exports and terminal layout. Add GPT-6.1 accounting, display, export and warm-cache regressions.

''',
}
for name, block in updates.items():
    p = root / name
    heading, body = p.read_text(encoding='utf-8').split('\n\n', 1)
    p.write_text(heading + '\n\n' + block + body, encoding='utf-8')

(root/'docs/v1.8.2-gpt61-sol.md').write_text('''# v1.8.2 — GPT-6.1 Sol

## Verified identity and Standard rates (2026-09-30)

The [official announcement](https://openai.com/index/introducing-gpt-6-1-sol/)
identifies the model as `gpt-6.1-sol`. The [credit-based Work/Codex rate card](https://help.openai.com/en/articles/11481834-chatgpt-rate-card-business-enterpriseedu-credit-based-pricing)
lists Standard reference credits per million tokens as follows:

| Model | Uncached input | Cached input | Output |
| --- | ---: | ---: | ---: |
| GPT-6.1 Sol | 50 | 2.5 | 250 |
| GPT-6 Sol | 50 | 5 | 250 |

The cached-input rate is halved, not the whole task cost. The new model must not
be an alias of GPT-6 Sol or Astra. Input already includes cached input; reasoning
tokens remain a detail of output, not a second charge.

Only the canonical ID and an exact `gpt-6.1-sol-YYYY-MM-DD` pattern are mapped.
Dated spellings are tool compatibility, not a claim that a dated endpoint exists.
Existing `gpt-6`/`gpt6` aliases still mean Astra. Generic `gpt-6.1`, Ultrafast,
Pro, WM and arbitrary preview suffixes are not silently mapped to Standard Sol.

## Fast: reference scale versus purchased credits

The current official credit-based page distinguishes two quantities:

- Included subscription allowance: Fast consumes **2.5x** Standard allowance.
- Purchased credits: Fast is billed at **2x** Standard credits.

This subscription usage profiler retains its **allowance-oriented reference
coordinate**, using 2.5x for GPT-6.1 Sol Fast/priority, as it already does for
GPT-6 Astra/Sol/Luna. This keeps credits and learned weekly percentages on the
same scale. It is not a purchased-credit invoice calculator or a claim that
current paid Fast requests cost 2.5x. The terminal adds a note when this model's
Fast usage (or an explicit Unknown-as-Fast assumption) contributes to the report.

The resulting Fast reference tuple is 125 / 6.25 / 625; the purchased-credit
billing tuple would be 100 / 5 / 500. Only the former is used by this tool's
existing reference/weekly path. No separate billing mode is introduced here.
No other model's rate or Fast multiplier is changed. This section supersedes
older documentation's unqualified descriptions of GPT-6 Fast credit billing.

## Integration and compatibility

The new ID displays as `6.1 Sol` in session, agent and model lists. Session/TOTAL,
1H, components, tiers, agents and JSON/CSV all use the shared pricing functions.
Sort order remains Standard unit price (input, output, cached input), not model
capability: when both appear, `6 Sol` sorts before `6.1 Sol` because its cached
input is more expensive. Astra remains ahead of both. No layout changes.

Existing schema-3 cached events contain model IDs and tokens, not frozen prices.
The next query prices already indexed GPT-6.1 Sol records and replays current
quota blocks with the new map. Blocks previously excluded only for this missing
rate can become complete or assumed-tier evidence. Other exclusions remain.
No cache rebuild or deletion, rate-coordinate migration, new dependency or
network call is needed. The v1.8.0 calibration policy and keys remain unchanged;
this is additive support, not a repricing of previously priceable usage.

## Limits and validation

Unknown tiers retain the existing Standard assumption; `--fast` affects only
Unknown segments, never detected Standard/Fast. Flex and unpriced variants
remain partial. Ultrafast support is not part of this update.

`WEEKLY` is still a backend snapshot and `WEEKLY≈` remains an empirical local
estimate, not an exact bill or guaranteed quota bound. Adding a model does not
prove that an old LOW scale is accurate; sufficient current quota evidence is
still needed. No undocumented included-allowance factor is added.

Synthetic regressions cover identities, lower cache pricing, Standard/Fast
segments, Unknown/Flex, price order, totals/exports and a warm-cache upgrade from
unpriced events to current quota evidence with zero transcript rereads.
''', encoding='utf-8')
