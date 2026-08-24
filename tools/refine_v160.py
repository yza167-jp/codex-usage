from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing anchor: {label}")
    return text.replace(old, new, 1)


script = Path("codex-usage")
s = script.read_text(encoding="utf-8")

old = '''        if event_type in ("thread_settings_applied", "thread_settings", "turn_context"):
            model = _mapping_model(payload)
            tier = _mapping_service_tier(payload)
            if model:
                current_model = model
            if tier is not None:
                current_service_tier = tier
        else:
'''
new = '''        if event_type == "thread_settings_applied":
            # ThreadSettingsApplied carries a full ThreadSettingsSnapshot. Its
            # optional service_tier field is omitted for the Standard/default
            # tier, so absence here must actively clear an earlier Fast state.
            model = _mapping_model(payload)
            tier = _mapping_service_tier(payload)
            if model:
                current_model = model
            current_service_tier = tier if tier is not None else SERVICE_TIER_STANDARD
        elif event_type in ("thread_settings", "turn_context"):
            model = _mapping_model(payload)
            tier = _mapping_service_tier(payload)
            if model:
                current_model = model
            if tier is not None:
                current_service_tier = tier
        else:
'''
s = replace_once(s, old, new, "thread_settings_applied semantics")

old = '''    if tier == SERVICE_TIER_UNKNOWN:
        if assume_fast_unknown:
            return FAST_MULTIPLIERS.get(model, 1.0), True
        # Standard is a conservative lower bound when this model supports Fast.
        return 1.0, model not in FAST_MULTIPLIERS
'''
new = '''    if tier == SERVICE_TIER_UNKNOWN:
        if assume_fast_unknown:
            multiplier = FAST_MULTIPLIERS.get(model)
            return (multiplier, True) if multiplier is not None else (1.0, False)
        # Standard is a conservative lower bound when this model supports Fast.
        return 1.0, model not in FAST_MULTIPLIERS
'''
s = replace_once(s, old, new, "unknown Fast multiplier completeness")
script.write_text(s, encoding="utf-8")


tests = Path("tests/test_codex_usage.py")
t = tests.read_text(encoding="utf-8")
insert = '''    def test_v160_full_settings_snapshot_without_tier_clears_fast(self):
        sid = "019ffabc-1234-7000-8000-123456789aab"
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / f"rollout-{sid}.jsonl"
            records = [
                {"timestamp": now.isoformat(), "type": "session_meta", "payload": {"id": sid, "model_provider": "openai"}},
                {"timestamp": now.isoformat(), "type": "event_msg", "payload": {"type": "thread_settings_applied", "thread_settings": {"model": "gpt-5.6-sol", "service_tier": "priority"}}},
                {"timestamp": (now + self.mod.timedelta(seconds=1)).isoformat(), "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 1_000_000, "total_tokens": 1_000_000}}}},
                {"timestamp": (now + self.mod.timedelta(seconds=2)).isoformat(), "type": "event_msg", "payload": {"type": "thread_settings_applied", "thread_settings": {"model": "gpt-5.6-sol"}}},
                {"timestamp": (now + self.mod.timedelta(seconds=3)).isoformat(), "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 2_000_000, "total_tokens": 2_000_000}}}},
            ]
            path.write_text("".join(json.dumps(r) + "\\n" for r in records), encoding="utf-8")
            session = self.mod.parse_rollout(path)
            deltas = self.mod.compute_deltas(session, {sid: session})
            self.assertEqual([d[2] for d in deltas], ["fast", "standard"])

    def test_v160_fast_fallback_does_not_override_detected_standard(self):
        usage = self.mod.Usage(input_tokens=1_000_000, total_tokens=1_000_000)
        standard = self.mod.usage_key("gpt-5.6-sol", "standard")
        credits, complete = self.mod._credit_for_usage_with_completeness(standard, usage, True)
        self.assertAlmostEqual(credits, 125.0)
        self.assertTrue(complete)

    def test_v160_unknown_fast_without_published_multiplier_stays_partial(self):
        usage = self.mod.Usage(input_tokens=1_000_000, total_tokens=1_000_000)
        unknown = self.mod.usage_key("gpt-5.3-codex", "unknown")
        credits, complete = self.mod._credit_for_usage_with_completeness(unknown, usage, True)
        self.assertAlmostEqual(credits, 43.75)
        self.assertFalse(complete)

'''
anchor = '    def test_v160_cache_schema_persists_service_tier(self):\n'
if "test_v160_full_settings_snapshot_without_tier_clears_fast" not in t:
    t = replace_once(t, anchor, insert + anchor, "test insertion")
tests.write_text(t, encoding="utf-8")


readme = Path("README.md")
r = readme.read_text(encoding="utf-8")
marker = "The v1.6 cache schema re-indexes token events once so each event can store `service_tier`."
if "full settings snapshot" not in r:
    r = replace_once(
        r,
        marker,
        "A persisted `thread_settings_applied` item is a full settings snapshot: when its optional `service_tier` field is absent, v1.6 treats it as Standard/default instead of carrying an earlier Fast setting forward.\n\n" + marker,
        "README snapshot semantics",
    )
readme.write_text(r, encoding="utf-8")


zh = Path("README.zh-CN.md")
z = zh.read_text(encoding="utf-8")
old_zh = '`--fast` 现在只会对无法从本地记录确定档位的 Unknown 段对支持的模型应用内置 Fast multiplier。由于历史 service tier 并不总是可靠写入 token event，`--fast` 的含义是“假设本次报告里的可用 usage 都使用 Fast”。'
new_zh = '`codex-usage` 会从持久化的 `turn_context` / `thread_settings_applied` 设置重建实际档位；`priority` 视为 Fast。缺少档位标记时默认按 Standard 给出保守下界；`--fast` 只把这些 Unknown 段按 Fast 估算，不会覆盖已经识别出的 Standard / Fast。'
if old_zh in z:
    z = z.replace(old_zh, new_zh, 1)
zh.write_text(z, encoding="utf-8")


changelog = Path("CHANGELOG.md")
c = changelog.read_text(encoding="utf-8")
marker = '- Normalized `priority`/`fast` to Fast and `default`/null to Standard; one session can now contain separately priced Standard and Fast segments.\n'
addition = marker + '- Treated an omitted `service_tier` in the full `thread_settings_applied` snapshot as Standard/default, preventing stale Fast state after Fast is switched off.\n'
if "preventing stale Fast state" not in c:
    c = replace_once(c, marker, addition, "changelog semantics")
changelog.write_text(c, encoding="utf-8")
