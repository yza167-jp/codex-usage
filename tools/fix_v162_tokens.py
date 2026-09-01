from pathlib import Path

script = Path("codex-usage")
text = script.read_text(encoding="utf-8")
old = '''            if scaled >= 100:
                text = f"{scaled:.0f}"
            elif scaled >= 10:
                text = f"{scaled:.1f}"
            else:
                text = f"{scaled:.2f}"
            return text.rstrip("0").rstrip(".") + suffix
'''
new = '''            if scaled >= 100:
                return f"{scaled:.0f}{suffix}"
            if scaled >= 10:
                text = f"{scaled:.1f}"
            else:
                text = f"{scaled:.2f}"
            return text.rstrip("0").rstrip(".") + suffix
'''
if old not in text:
    raise SystemExit("compact-token implementation anchor missing")
script.write_text(text.replace(old, new, 1), encoding="utf-8")

tests = Path("tests/test_codex_usage.py")
test_text = tests.read_text(encoding="utf-8")
anchor = '        self.assertLessEqual(self.mod.display_width(self.mod.token_triplet_text(usage)), 18)\n'
addition = anchor + '        self.assertEqual(self.mod.human_tokens_compact(100_000_000), "100M")\n'
if 'human_tokens_compact(100_000_000)' not in test_text:
    if anchor not in test_text:
        raise SystemExit("compact-token test anchor missing")
    test_text = test_text.replace(anchor, addition, 1)
tests.write_text(test_text, encoding="utf-8")
