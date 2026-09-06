from pathlib import Path
import hashlib

root = Path('.')
p = root / 'codex-usage'
s = p.read_text(encoding='utf-8')
assert hashlib.sha1(b'blob ' + str(len(p.read_bytes())).encode() + b'\0' + p.read_bytes()).hexdigest() == '7e662ff6275732ecd945fc9ab2e8c11e3019d3ac'
s = s.replace('VERSION = "1.7.2"', 'VERSION = "1.7.3"', 1)
anchor = 'def model_names(models: Iterable[str]) -> List[str]:\n'
new = '''def model_display_sort_key(key: str) -> Tuple[bool, float, float, float, str]:
    """Sort model identities by descending Standard reference unit price.

    Uncached input is the primary comparison, then output and cached input.
    Equal rates use the canonical ID as a deterministic tie-break. Unknown
    prices sort last without inventing a rate. Neither accumulated spend nor
    Fast usage changes which model represents a mixed session.
    """
    model, _ = split_usage_key(key)
    rates = RATE_CARD.get(model)
    if rates is None:
        return True, 0.0, 0.0, 0.0, model
    input_rate, cached_rate, output_rate = rates
    return False, -input_rate, -output_rate, -cached_rate, model


def model_tier_display_sort_key(key: str) -> Tuple:
    """Keep each model together; within a model show Fast before Standard.

    Flex/Unknown stay explicitly unresolved and follow the known tiers. This
    is presentation ordering only; it does not resolve or price missing tiers.
    """
    _, tier = split_usage_key(key)
    tier_rank = SERVICE_TIER_ORDER.index(tier) if tier in SERVICE_TIER_ORDER else len(SERVICE_TIER_ORDER)
    return model_display_sort_key(key), tier_rank


'''
assert s.count(anchor) == 1
s = s.replace(anchor, new + anchor, 1)
old = '''            out.append(model)
    return out


def model_label'''
assert s.count(old) == 1
s = s.replace(old, '''            out.append(model)
    return sorted(out, key=model_display_sort_key)


def model_label''', 1)
old = '            model_rows.sort(key=lambda x: (x[3] if x[3] is not None else -1), reverse=True)'
assert s.count(old) == 1
s = s.replace(old, '''            model_rows.sort(key=lambda x: model_tier_display_sort_key(usage_key(x[0], x[1])))''', 1)
old = '        model_breakdown.sort(key=lambda x: x["credit_estimate"] if x["credit_estimate"] is not None else -1, reverse=True)'
assert s.count(old) == 1
s = s.replace(old, '''        model_breakdown.sort(key=lambda x: model_tier_display_sort_key(
            usage_key(x["model"], x["service_tier"])
        ))''', 1)
p.write_text(s, encoding='utf-8')
assert hashlib.sha256(p.read_bytes()).hexdigest() == '481c2d856a983ee6d28f5b92a2c663610ce6c7c71cac71839bb5893e46ae10a9'
p = root / 'tests/test_model_display.py'
s = p.read_text(encoding='utf-8')
s = s.replace('5.6 Sol / 5.6 Luna / 6 Astra', '6 Astra / 5.6 Sol / 5.6 Luna')
s = s.replace('5.6 Sol / 6 Astra', '6 Astra / 5.6 Sol')
s = s.replace('5.6 Sol +', '6 Astra +')
p.write_text(s, encoding='utf-8')
p = root / 'tests/test_codex_usage.py'
s = p.read_text(encoding='utf-8').replace('self.assertIn("1.7.2", proc.stdout)', 'self.assertIn("1.7.3", proc.stdout)')
p.write_text(s, encoding='utf-8')
eng = '''## v1.7.3: highest-priced model first

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

'''
zh = '''## v1.7.3：优先显示单价更高的模型

多个模型共用一个 session 时，按内置 Standard 参考单价降序显示，不再按出现
先后或累计消耗排序。例如 Astra + Sol + Luna 的主行显示 `6 Astra +2`，
续行显示 `Models: 6 Astra / 5.6 Sol / 5.6 Luna`。主表、模型详情、agent 的
模型列表和 JSON/CSV 中的模型列表采用同一规则。

先比较未缓存输入单价，再比较输出、缓存输入单价；同价按规范化模型 ID 稳定
排序。Fast 不改变模型本身的排序位置；同模型内部先 Fast、后 Standard，再列
出未解决的 Flex/Unknown。未定价模型保留在最后，不推测价格或能力高低。

不改变 PROJECT/SESSION 列宽、144 格上限、session/agent 行顺序、金额、weekly
校准或缓存结构；JSON/CSV 字段和数值保持兼容，仅模型列表顺序改变。
照常运行即可，无需新参数或重建 cache。

'''
for filename, section in [('README.md', eng), ('README.zh-CN.md', zh)]:
    p = root / filename
    s = p.read_text(encoding='utf-8')
    assert s.startswith('# codex-usage\n\n')
    p.write_text(s.replace('# codex-usage\n\n', '# codex-usage\n\n' + section, 1), encoding='utf-8')
p = root / 'CHANGELOG.md'
s = p.read_text(encoding='utf-8')
section = '''## 1.7.3 — 2026-09-06

- Sort model identities by descending Standard reference unit price, so mixed Astra/Sol/Luna sessions display Astra first irrespective of usage volume or insertion order.
- Apply the same order to inline MODEL(S), compact first-model +N labels, complete Models continuations, model details, agent model lists, and JSON/CSV model lists.
- Use uncached-input, output, cached-input rates and canonical ID tie-breaks; group tiers per model with Fast before Standard. Keep unpriced models visible last without guessing prices.
- Preserve session/agent row order, numeric accounting, Fast pricing, weekly calibration, cache schema and the 144-cell PROJECT/SESSION layout. No cache rebuild required.
- Add price-order, tier, unpriced-model, export compatibility and presentation-only regressions.

'''
assert s.startswith('# Changelog\n\n')
p.write_text(s.replace('# Changelog\n\n', '# Changelog\n\n'+section,1), encoding='utf-8')
