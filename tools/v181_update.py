"""Apply the additive v1.8.1 model support patch to the v1.8.0 source."""
from pathlib import Path


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Expected one patch anchor: ' + old[:100])
    return text.replace(old, new, 1)


path = Path('codex-usage')
s = path.read_text(encoding='utf-8')
s = replace_once(s, 'VERSION = "1.8.0"', 'VERSION = "1.8.1"')
s = replace_once(s, 'GPT6_RATE_CARD_AS_OF = "2026-09-05"',
                 'GPT6_RATE_CARD_AS_OF = "2026-09-27"')
s = replace_once(s,
    '# Do not invalidate complete historical calibration: no previously priced model\n'
    '# or tier changes cost. Old incomplete intervals remain excluded, not relabeled.',
    '# Additive rates do not change previously priced model/tier costs or cached\n'
    '# token coordinates. Current quota blocks are replayed from raw snapshots and\n'
    '# deltas on each query, so formerly unpriced Sol/Luna blocks are re-evaluated;\n'
    '# legacy incomplete credit scalars are never promoted without replay.')
s = replace_once(s,
    "# about current purchased-credit promotions. GPT-6 Astra's Work/Codex reference\n"
    "# rates (checked 2026-09-05) are documented in docs/v1.7.0-gpt6.md.",
    '# about current purchased-credit promotions. GPT-6 Work/Codex reference rates\n'
    '# (checked 2026-09-27) include distinct Astra, Sol and Luna entries; see\n'
    '# docs/v1.8.1-gpt6-sol-luna.md. They are not fixed Plus/Pro quota conversions.')
s = replace_once(s,
    '    "gpt-6-astra": (250.0, 25.0, 1250.0),',
    '    "gpt-6-astra": (250.0, 25.0, 1250.0),\n'
    '    "gpt-6-sol": (50.0, 5.0, 250.0),\n'
    '    "gpt-6-luna": (2.5, 0.25, 12.5),')
s = replace_once(s,
    '    "gpt-6-astra": 2.5,  # Work/Codex, not the API Fast rate',
    '    "gpt-6-astra": 2.5,  # Work/Codex, not the API Fast rate\n'
    '    "gpt-6-sol": 2.5,\n'
    '    "gpt-6-luna": 2.5,')
s = replace_once(s,
    '# Exact shorthand aliases are a tool compatibility convention. Match dated\n'
    '    # Astra IDs narrowly; never price every gpt-6-* variant as the base model.',
    '# Existing shorthand aliases still mean Astra for backward compatibility.\n'
    '    # Dated IDs retain their exact family; never price every gpt-6-* variant\n'
    '    # as Astra or infer a rate for an unverified Pro/preview/WM suffix.')
s = replace_once(s,
    '    if re.fullmatch(r"gpt-6-astra-\\d{4}-\\d{2}-\\d{2}", s):\n'
    '        return "gpt-6-astra"',
    '    dated = re.fullmatch(r"(gpt-6-(?:astra|sol|luna))-\\d{4}-\\d{2}-\\d{2}", s)\n'
    '    if dated:\n'
    '        return dated.group(1)')
s = replace_once(s,
    '        "gpt-6-astra": "6 Astra",',
    '        "gpt-6-astra": "6 Astra",\n'
    '        "gpt-6-sol": "6 Sol",\n'
    '        "gpt-6-luna": "6 Luna",')
s = replace_once(s,
    'def service_tier_display(tier: str, compact: bool = False) -> str:',
    '''def unpriced_model_names(buckets: Dict[str, Bucket]) -> List[str]:
    """Identify missing model rates, separately from unresolved service tiers."""
    return model_names(
        key for bucket in buckets.values() for key in bucket.usage_by_model
        if split_usage_key(key)[0] not in RATE_CARD
    )


def unpriced_model_notes(buckets: Dict[str, Bucket]) -> List[str]:
    """Report missing canonical IDs without silently treating their usage as zero."""
    names = unpriced_model_names(buckets)
    if not names:
        return []
    return [
        "Unpriced models (selected period): " + " / ".join(names),
        "Tokens retained; reference credits and WEEKLY estimates exclude these models. "
        "Update codex-usage for newer rate support.",
    ]


def service_tier_display(tier: str, compact: bool = False) -> str:''')
s = replace_once(s,
    '    lines.append("")\n\n    if not rows:\n'
    '        lines.append("No token_count usage found for this period.")',
    '    for note in unpriced_model_notes(buckets):\n'
    '        lines.extend(color.wrap(part, color.YELLOW)\n'
    '                     for part in wrap_display_words(note, terminal_width))\n'
    '    lines.append("")\n\n    if not rows:\n'
    '        lines.append("No token_count usage found for this period.")')
path.write_text(s, encoding='utf-8')

p = Path('tests/test_codex_usage.py')
t = p.read_text(encoding='utf-8')
t = replace_once(t, 'self.assertIn("1.8.0", proc.stdout)', 'self.assertIn("1.8.1", proc.stdout)')
p.write_text(t, encoding='utf-8')

# Preserve all old tests; only make the banner assertion follow its dated constant.
p = Path('tests/test_gpt6.py')
t = p.read_text(encoding='utf-8')
t = replace_once(t, 'self.assertIn("GPT-6 2026-09-05", table)',
                 'self.assertIn(f"GPT-6 {m.GPT6_RATE_CARD_AS_OF}", table)')
p.write_text(t, encoding='utf-8')

notes = '''## 1.8.1 — 2026-09-27

- Add distinct GPT-6 Sol (50 / 5 / 250) and GPT-6 Luna (2.5 / 0.25 / 12.5) Work/Codex reference credit rates per million uncached-input / cached-input / output tokens; both support a 2.5x Fast multiplier.
- Recognize canonical and narrowly matched dated Sol/Luna IDs, displaying `6 Sol` and `6 Luna`; preserve Astra aliases and do not guess other GPT-6 variant prices.
- Restore session/TOTAL/1H, component, agent/model/tier, weekly and JSON/CSV estimates for already indexed Sol/Luna usage. Keep price-descending model order based on reference unit price, not generation.
- Name missing-rate models explicitly in terminal reports. Retain their tokens and unknown/partial results; a known model with an Unknown tier is not reported as an unpriced model.
- Re-evaluate current-period quota blocks from existing raw snapshots and token deltas, including blocks previously excluded for missing Sol/Luna rates. Preserve schema-3 token caches, all quota history, calibration policy and previously priced model rates. No rebuild is needed.
- Add regressions for Standard/Fast/Unknown, independent model identities, mixed subagents/exports, all-unpriced warnings, warm-cache upgrade and excluded-to-eligible quota replay.

'''
p = Path('CHANGELOG.md')
p.write_text(replace_once(p.read_text(encoding='utf-8'), '# Changelog\n\n', '# Changelog\n\n' + notes), encoding='utf-8')

intro_en = '''## v1.8.1: GPT-6 Sol and Luna

`gpt-6-sol` and `gpt-6-luna` now have **separate** reference rates and display as
`6 Sol` and `6 Luna`. Standard rates, in credits per million uncached input /
cached input / output tokens, are **50 / 5 / 250** and **2.5 / 0.25 / 12.5**;
Fast/priority is **2.5x** for both. They are not aliases of Astra or GPT-5.6.
Model lists remain sorted by Standard reference unit price, not version number.

**No cache rebuild.** Previously indexed Sol/Luna events become priceable on the
next query, and current quota blocks are replayed from existing raw snapshots
and deltas. All historical quota records and the v1.8.0 calibration policy are
preserved. Enough eligible quota movement is still needed for a current delta
scale; fallback/LOW labels remain honest. The prices are Work/Codex reference
credits, not a guaranteed Plus/Pro weekly-allowance conversion.

A terminal report with other missing model rates now names their canonical IDs
instead of showing unexplained dashes. Their tokens remain counted; their credit
and weekly estimates are unavailable/partial, never silently zero. Unknown
service tiers of priced models remain a different condition.
See [rates, compatibility and validation](docs/v1.8.1-gpt6-sol-luna.md).

'''
intro_zh = '''## v1.8.1：支持 GPT-6 Sol 和 Luna

新增 `gpt-6-sol`、`gpt-6-luna` 的独立参考费率，显示为 **6 Sol / 6 Luna**。
每百万未缓存输入／缓存输入／输出 tokens 的标准参考 credits 分别为
**50 / 5 / 250** 和 **2.5 / 0.25 / 12.5**；Fast/priority 均为 **2.5 倍**。
不会把它们当成 Astra 或 GPT-5.6 的别名。模型列表仍按标准参考单价降序，
不是按型号数字或代际排序。

**无需重建 cache。** 已索引的 Sol/Luna tokens 在下一次查询直接恢复计价；
当前周期的校准区间会利用已有原始快照和 token 增量重新评估，不沿用旧的
“未定价”结论。保留所有 quota 历史和 v1.8.0 校准策略；当前 delta 估算仍需
足够的可用额度变化，不能保证每次都能立刻摆脱历史 fallback 或 LOW。
这些是 Work/Codex 参考 credits，不是 Plus/Pro weekly 的官方固定换算率。

遇到其他缺少费率的模型时，终端会明确列出其模型 ID，说明 tokens 已保留、
对应 credits/weekly 无法计价或仅部分可用；不再只有满屏 `—`。已知模型但
档位为 `?` 不等于模型未定价。详见[费率与兼容说明](docs/v1.8.1-gpt6-sol-luna.md)。

'''
for name, intro in [('README.md', intro_en), ('README.zh-CN.md', intro_zh)]:
    p = Path(name)
    p.write_text(replace_once(p.read_text(encoding='utf-8'), '# codex-usage\n\n',
                             '# codex-usage\n\n' + intro), encoding='utf-8')

Path('docs/v1.8.1-gpt6-sol-luna.md').write_text('''# v1.8.1 — GPT-6 Sol/Luna reference accounting

## Rate sources (checked 2026-09-27)

The official [credit-based ChatGPT Work/Codex rate card](https://help.openai.com/en/articles/11481834-chatgpt-rate-card-business-enterpriseedu-credit-based-pricing)
lists these Standard reference rates in credits per million tokens:

| Model ID | Uncached input | Cached input | Output | Fast / priority |
| --- | ---: | ---: | ---: | ---: |
| `gpt-6-astra` | 250 | 25 | 1250 | 2.5x |
| `gpt-6-sol` | 50 | 5 | 250 | 2.5x |
| `gpt-6-luna` | 2.5 | 0.25 | 12.5 | 2.5x |

The same page explicitly lists the 2.5x Work/Codex Fast multiplier for all
three GPT-6 models. The [Enterprise token-based rate card](https://help.openai.com/en/articles/20001415-chatgpt-rate-card-enterprise-token-based-pricing)
also identifies the models and Work/Codex multiplier; this tool does not import
its USD pricing or treat it as the user's bill. The credit-based page describes
workspace pricing, not a fixed included-allowance conversion for Plus/Pro.

This patch adds only the missing Sol/Luna reference entries. Previously embedded
GPT-5.x reference prices remain pinned: it does not retroactively replace them
with purchased-credit promotions or alter the existing calibration scale.
No undocumented model-specific included-allowance multiplier is introduced.

## Identity, tiers and display

Canonical IDs and exact `gpt-6-{astra,sol,luna}-YYYY-MM-DD` spellings are recognized;
dates are a tool compatibility convention, not an assertion that any given dated
model is offered. Existing `gpt-6` / `gpt6` shorthands continue to mean Astra.
Pro, WM, preview and arbitrary suffixes are not collapsed into priced families.

Fast is applied to its own token segments, not the whole session. Unknown tiers
use the existing explicit Standard assumption (`--fast` changes only Unknown).
Flex and unverified variants retain incomplete/unpriced semantics. Cached input
is a subset of input; reasoning output is not charged again on top of output.

All session/TOTAL/1H, model/tier/agent/component tables and JSON/CSV exports use
the shared rates. Models still sort by the pinned Standard unit-price tuple,
not generation; thus GPT-5.6 Sol can sort before GPT-6 Sol. PROJECT/SESSION
columns, complete model continuation lines and the 144-cell cap are unchanged.

Unpriced IDs in the selected period are listed explicitly in a wrapped terminal
warning. All-unpriced reports retain tokens and unknown estimates (`—`). Mixed
reports keep known costs with partial markers; unpriced does not mean free.
This warning concerns the selected period, not every model in the current week.

## Existing caches and calibration

Schema-3 cached events store model IDs and tokens, not frozen prices. No rescan,
manual rebuild, or cache deletion is required. Each query replays current-period
quota blocks from stored raw snapshots and indexed deltas with the current map.
Blocks excluded only because Sol/Luna lacked rates become complete or
assumed-tier blocks when replayed; blocks with other missing information remain
excluded. Raw history is retained. Old incomplete scalar observations are not
silently upgraded to complete observations.

The reference calibration key and v1.8.0 policy stay unchanged because no
previously priceable model changes cost. Historical LOW priors remain only
fallbacks, and sufficient current evidence takes priority as before. Reset,
saturation, tier assumptions, missing history and sparse quota snapshots can
still prevent a current delta estimate. A missing price being fixed does not
by itself validate a weekly conversion or resolve old Unknown tiers.

## Verification scope

Synthetic tests cover separate families, cache/reasoning arithmetic, per-segment
Fast, strict suffixes, price ordering, mixed-agent rollup, JSON/CSV/terminal
results, Unknown versus unpriced warnings, and an old warm-cache upgrade.
The upgrade regression starts with Sol/Luna absent from the rate map, saves
excluded current quota blocks, then enables the rates and verifies that the same
token events and raw quota snapshots produce usable current evidence without
JSONL rereads. Existing regressions remain in the suite.

These are tests of the implementation, not a replay or audit of private user
transcripts. `WEEKLY≈` remains an estimate; a partial value uses `?`, not a
claimed provider-quota lower bound. No account tokens or user transcripts are
included in the fixtures.
''', encoding='utf-8')
