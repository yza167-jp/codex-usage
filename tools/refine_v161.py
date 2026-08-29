from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing anchor: {label}")
    return text.replace(old, new, 1)


script = Path("codex-usage")
s = script.read_text(encoding="utf-8")
old = '''def _disambiguate_bucket_titles(buckets: Dict[str, Bucket]) -> None:
    """Give exact duplicate visible labels a stable short-session suffix."""
    grouped: Dict[str, List[Bucket]] = {}
    for bucket in buckets.values():
        key = _clean_thread_label(bucket.title).casefold()
        grouped.setdefault(key, []).append(bucket)
    for group in grouped.values():
        if len(group) < 2:
            continue
        for bucket in group:
            suffix = bucket.session_id[:12]
            if suffix and not bucket.title.endswith(suffix):
                bucket.title = f"{bucket.title} · {suffix}"
'''
new = '''def _disambiguate_bucket_titles(buckets: Dict[str, Bucket]) -> None:
    """Give exact duplicate labels a stable marker that survives truncation."""
    grouped: Dict[str, List[Bucket]] = {}
    for bucket in buckets.values():
        key = _clean_thread_label(bucket.title).casefold()
        grouped.setdefault(key, []).append(bucket)
    for group in grouped.values():
        if len(group) < 2:
            continue
        for bucket in group:
            compact_id = bucket.session_id.replace("-", "")
            marker = f"#{compact_id[-6:]}" if compact_id else "#dup"
            # Keep project context first, then insert the marker before the
            # long prompt/name so a narrow SESSION column still distinguishes it.
            if bucket.title.startswith("[") and "]" in bucket.title:
                close = bucket.title.find("]") + 1
                prefix = bucket.title[:close]
                rest = bucket.title[close:].lstrip()
                bucket.title = f"{prefix} {marker} {rest}" if rest else f"{prefix} {marker}"
            else:
                bucket.title = f"{marker} {bucket.title}"
'''
s = replace_once(s, old, new, "duplicate title marker")
script.write_text(s, encoding="utf-8")


tests = Path("tests/test_codex_usage.py")
t = tests.read_text(encoding="utf-8")
old_test = '''        self.assertNotEqual(first.title, second.title)
        self.assertTrue(first.title.endswith(first.session_id[:12]))
        self.assertTrue(second.title.endswith(second.session_id[:12]))
'''
new_test = '''        self.assertNotEqual(first.title, second.title)
        self.assertTrue(first.title.startswith("[project] #"))
        self.assertTrue(second.title.startswith("[project] #"))
        self.assertIn(first.session_id.replace("-", "")[-6:], first.title)
        self.assertIn(second.session_id.replace("-", "")[-6:], second.title)
'''
t = replace_once(t, old_test, new_test, "duplicate title test")
tests.write_text(t, encoding="utf-8")
