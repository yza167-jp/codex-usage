from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing anchor: {label}")
    return text.replace(old, new, 1)


script = Path("codex-usage")
s = script.read_text(encoding="utf-8")
s = replace_once(s, 'VERSION = "1.6.1"', 'VERSION = "1.6.2"', "version")
s = replace_once(
    s,
    "REPORT_MAX_WIDTH = len(STATUS_NOTE)\n",
    "REPORT_MAX_WIDTH = len(STATUS_NOTE)\nWIDE_SUMMARY_INLINE_MIN_WIDTH = 116\n",
    "wide minimum constant",
)

helper_block = r'''

def shrink_widths_to_target(
    base_widths: Iterable[int],
    minimum_widths: Iterable[int],
    target_width: int,
    shrink_order: Iterable[int],
    gap: int = 2,
) -> List[int]:
    """Shrink selected columns without sacrificing the SESSION column first."""
    widths = list(base_widths)
    minimums = list(minimum_widths)
    if len(widths) != len(minimums):
        raise ValueError("base_widths and minimum_widths must have equal length")
    deficit = sum(widths) + gap * (len(widths) - 1) - target_width
    for idx in shrink_order:
        if deficit <= 0:
            break
        reducible = max(0, widths[idx] - minimums[idx])
        cut = min(reducible, deficit)
        widths[idx] -= cut
        deficit -= cut
    return widths


def human_tokens_compact(n: int) -> str:
    """Compact token count for the inline INPUT/CACHED/OUTPUT triplet."""
    value = max(0, int(n))
    for scale, suffix in (
        (1_000_000_000_000, "T"),
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    ):
        if value >= scale:
            scaled = value / scale
            if scaled >= 100:
                text = f"{scaled:.0f}"
            elif scaled >= 10:
                text = f"{scaled:.1f}"
            else:
                text = f"{scaled:.2f}"
            return text.rstrip("0").rstrip(".") + suffix
    return str(value)


def token_triplet_text(usage: Usage) -> str:
    """Render INPUT/CACHED/OUTPUT compactly while retaining all three values."""
    return "/".join((
        human_tokens_compact(usage.input_tokens),
        human_tokens_compact(usage.cached_input_tokens),
        human_tokens_compact(usage.output_tokens),
    ))


def fit_session_summary_title(title: str, width: int) -> str:
    """Keep both project context and task text visible in a narrow SESSION cell.

    A generic right-side truncation can spend the entire cell on a long prefix
    such as ``[atomic-cross-modal-transfer]``. This renderer reserves part of
    the cell for the actual Codex name/title and shortens the project tag first.
    """
    clean = _clean_thread_label(title)
    if width <= 0 or display_width(clean) <= width:
        return clean if width > 0 else ""
    match = re.match(r"^\[([^\]]+)\]\s*(.*)$", clean)
    if not match or not match.group(2):
        return truncate(clean, width)

    context, body = match.group(1), match.group(2)
    body_reserve = min(14, max(8, width // 3))
    marker = re.match(r"^(#[^\s]+)\s+", body)
    if marker:
        body_reserve = max(
            body_reserve,
            min(max(8, width - 6), display_width(marker.group(1)) + 5),
        )
    context_budget = max(3, width - body_reserve - 3)  # brackets + separating space
    context_text = truncate(context, context_budget)
    prefix = f"[{context_text}] "
    remaining = width - display_width(prefix)
    if remaining < 4:
        return truncate(clean, width)
    return prefix + truncate(body, remaining)


def summary_table_layout(
    terminal_width: int,
    wide: bool,
) -> Tuple[List[str], List[int], set, bool]:
    """Return headers, widths, numeric columns, and inline-wide status.

    At the canonical 144-cell report width, wide mode packs INPUT/CACHED/OUTPUT
    into one token triplet and dedicates 34 cells to SESSION. On narrow
    terminals, --wide falls back to the normal table plus token continuation
    lines rather than squeezing the project-aware label into an unreadable tag.
    """
    gap = 2
    if wide and terminal_width >= WIDE_SUMMARY_INLINE_MIN_WIDTH:
        headers = [
            "SESSION", "MODEL(S)", "TIER(S)", "WEEKLY≈", "1H≈", "CREDITS*",
            "TOKENS I/C/O", "CACHE TAX", "SHARE", "STATUS",
        ]
        base = [34, 12, 9, 9, 8, 9, 18, 9, 6, 12]
        minimums = [20, 10, 7, 8, 7, 8, 14, 8, 6, 10]
        widths = shrink_widths_to_target(
            base,
            minimums,
            terminal_width,
            (6, 1, 2, 9, 3, 4, 5, 7, 0),
            gap,
        )
        widths = fit_widths_to_target(widths, terminal_width, (0,), gap)
        return headers, widths, {3, 4, 5, 7, 8}, True

    headers = [
        "SESSION", "MODEL(S)", "TIER(S)", "WEEKLY≈", "1H≈", "CREDITS*",
        "CACHE TAX", "SHARE", "STATUS",
    ]
    base = [40, 19, 10, 10, 9, 10, 10, 7, 13]
    minimums = [12, 8, 5, 6, 5, 7, 7, 5, 7]
    widths = shrink_widths_to_target(
        base,
        minimums,
        terminal_width,
        (1, 2, 8, 3, 4, 5, 6, 7, 0),
        gap,
    )
    widths = fit_widths_to_target(widths, terminal_width, (0,), gap)
    return headers, widths, {3, 4, 5, 6, 7}, False
'''
s = replace_once(s, "\n\ndef make_buckets(\n", helper_block + "\n\ndef make_buckets(\n", "layout helpers")

old_layout = '''    gap = 2
    if wide:
        headers = ["SESSION", "MODEL(S)", "TIER(S)", "WEEKLY≈", "1H≈", "CREDITS*", "INPUT", "CACHED", "OUTPUT", "CACHE TAX", "SHARE", "STATUS"]
        fixed = [10, 10, 9, 10, 9, 9, 9, 10, 7, 13]
        fixed_total = sum(fixed) + gap * (len(headers) - 1)
        flexible = max(28, terminal_width - fixed_total)
        model_w = max(14, min(24, flexible // 3))
        session_w = max(18, flexible - model_w)
        widths = [session_w, model_w] + fixed
        align_right = {3, 4, 5, 6, 7, 8, 9, 10}
    else:
        headers = ["SESSION", "MODEL(S)", "TIER(S)", "WEEKLY≈", "1H≈", "CREDITS*", "CACHE TAX", "SHARE", "STATUS"]
        fixed = [10, 10, 9, 10, 10, 7, 13]
        fixed_total = sum(fixed) + gap * (len(headers) - 1)
        flexible = max(30, terminal_width - fixed_total)
        model_w = max(14, min(24, flexible // 3))
        session_w = max(20, flexible - model_w)
        widths = [session_w, model_w] + fixed
        align_right = {3, 4, 5, 6, 7}
'''
new_layout = '''    gap = 2
    headers, widths, align_right, wide_inline = summary_table_layout(
        terminal_width, wide
    )
'''
s = replace_once(s, old_layout, new_layout, "summary layout")

old_rows = '''        title = b.title + (f" (+{len(b.child_sessions)} sub)" if b.child_sessions else "")
        status = status_text(state, health, is_orphan)
        weekly_text = weekly_percent_text(credits, quota_calibration, complete)
        burn_weekly = weekly_percent_text(
            burn if burn is not None and burn > 0 else None, quota_calibration, burn_complete
        )

        if wide:
            row = [
                title, model_label(b.usage_by_model.keys()), tier_label(b.usage_by_model.keys()),
                weekly_text, burn_weekly, credit_text,
                human_tokens(u.input_tokens), human_tokens(u.cached_input_tokens),
                human_tokens(u.output_tokens), f"{cache_tax:.1f}" if cache_tax > 0 else "—",
                share_text, status,
            ]
            status_idx, title_idx, burn_idx, cache_idx = 11, 0, 4, 9
        else:
            row = [
                title, model_label(b.usage_by_model.keys()), tier_label(b.usage_by_model.keys()),
                weekly_text, burn_weekly, credit_text,
                f"{cache_tax:.1f}" if cache_tax > 0 else "—", share_text, status,
            ]
            status_idx, title_idx, burn_idx, cache_idx = 8, 0, 4, 6
'''
new_rows = '''        raw_title = b.title + (f" (+{len(b.child_sessions)} sub)" if b.child_sessions else "")
        title = fit_session_summary_title(raw_title, widths[0])
        status = status_text(state, health, is_orphan)
        weekly_text = weekly_percent_text(credits, quota_calibration, complete)
        burn_weekly = weekly_percent_text(
            burn if burn is not None and burn > 0 else None, quota_calibration, burn_complete
        )

        if wide_inline:
            row = [
                title, model_label(b.usage_by_model.keys()), tier_label(b.usage_by_model.keys()),
                weekly_text, burn_weekly, credit_text, token_triplet_text(u),
                f"{cache_tax:.1f}" if cache_tax > 0 else "—", share_text, status,
            ]
            status_idx, title_idx, burn_idx, cache_idx = 9, 0, 4, 7
        else:
            row = [
                title, model_label(b.usage_by_model.keys()), tier_label(b.usage_by_model.keys()),
                weekly_text, burn_weekly, credit_text,
                f"{cache_tax:.1f}" if cache_tax > 0 else "—", share_text, status,
            ]
            status_idx, title_idx, burn_idx, cache_idx = 8, 0, 4, 6
'''
s = replace_once(s, old_rows, new_rows, "summary rows")

s = replace_once(
    s,
    "        lines.append(fmt_row(row, styles))\n\n    total_usage = Usage()\n",
    '''        lines.append(fmt_row(row, styles))
        if wide and not wide_inline:
            token_line = f"  TOKENS I/C/O  {token_triplet_text(u)}"
            lines.append(color.wrap(truncate(token_line, terminal_width), color.DIM))

    total_usage = Usage()
''',
    "narrow wide continuation",
)

old_total = '''    if wide:
        total_row = [
            "TOTAL", "", "", total_weekly_text, total_burn_weekly, total_credit_text,
            human_tokens(total_usage.input_tokens), human_tokens(total_usage.cached_input_tokens),
            human_tokens(total_usage.output_tokens), f"{total_cache_tax:.1f}" if total_cache_tax else "—",
            "100%" if known_credit_total > 0 else "—", "",
        ]
    else:
        total_row = [
            "TOTAL", "", "", total_weekly_text, total_burn_weekly, total_credit_text,
            f"{total_cache_tax:.1f}" if total_cache_tax else "—",
            "100%" if known_credit_total > 0 else "—", "",
        ]
    lines.append(color.wrap("  ".join("-" * w for w in widths), color.DIM))
    lines.append(fmt_row(total_row, {i: "total" for i in range(len(total_row))}))
'''
new_total = '''    if wide_inline:
        total_row = [
            "TOTAL", "", "", total_weekly_text, total_burn_weekly, total_credit_text,
            token_triplet_text(total_usage),
            f"{total_cache_tax:.1f}" if total_cache_tax else "—",
            "100%" if known_credit_total > 0 else "—", "",
        ]
    else:
        total_row = [
            "TOTAL", "", "", total_weekly_text, total_burn_weekly, total_credit_text,
            f"{total_cache_tax:.1f}" if total_cache_tax else "—",
            "100%" if known_credit_total > 0 else "—", "",
        ]
    lines.append(color.wrap("  ".join("-" * w for w in widths), color.DIM))
    lines.append(fmt_row(total_row, {i: "total" for i in range(len(total_row))}))
    if wide and not wide_inline:
        lines.append(color.wrap(
            truncate(f"  TOKENS I/C/O  {token_triplet_text(total_usage)}", terminal_width),
            color.DIM,
        ))
'''
s = replace_once(s, old_total, new_total, "summary total")

s = replace_once(
    s,
    '''    if not wide:
        lines.append(color.wrap("  Use --wide to restore INPUT/CACHED/OUTPUT columns.", color.DIM))
''',
    '''    if not wide:
        lines.append(color.wrap("  Use --wide to add a compact INPUT/CACHED/OUTPUT token triplet.", color.DIM))
    elif not wide_inline:
        lines.append(color.wrap(
            "  At this terminal width, --wide token diagnostics use continuation lines to preserve SESSION readability.",
            color.DIM,
        ))
    else:
        lines.append(color.wrap("  TOKENS I/C/O = INPUT / CACHED / OUTPUT.", color.DIM))
''',
    "wide output note",
)

s = replace_once(
    s,
    'help="Show INPUT/CACHED/OUTPUT columns in the summary table.",',
    'help="Add a compact INPUT/CACHED/OUTPUT token triplet; narrow terminals use continuation lines.",',
    "wide help",
)
script.write_text(s, encoding="utf-8")


tests = Path("tests/test_codex_usage.py")
t = tests.read_text(encoding="utf-8")
t = replace_once(t, 'self.assertIn("1.6.1", proc.stdout)', 'self.assertIn("1.6.2", proc.stdout)', "test version")
insert = r'''
    def test_v162_wide_layout_preserves_session_width_at_report_cap(self):
        headers, widths, right, inline = self.mod.summary_table_layout(144, True)
        self.assertTrue(inline)
        self.assertIn("TOKENS I/C/O", headers)
        self.assertNotIn("INPUT", headers)
        self.assertGreaterEqual(widths[0], 34)
        self.assertEqual(sum(widths) + 2 * (len(widths) - 1), 144)
        self.assertEqual(right, {3, 4, 5, 7, 8})

    def test_v162_project_aware_truncation_keeps_project_and_task(self):
        raw = "[atomic-cross-modal-transfer] 读取 AGENTS.md、docs/PROJECT_STATUS.md"
        fitted = self.mod.fit_session_summary_title(raw, 34)
        self.assertLessEqual(self.mod.display_width(fitted), 34)
        self.assertTrue(fitted.startswith("[atomic"))
        self.assertIn("读取", fitted)
        self.assertNotEqual(fitted, self.mod.truncate(raw, 34))

    def test_v162_compact_token_triplet(self):
        usage = self.mod.Usage(
            input_tokens=95_160_000,
            cached_input_tokens=92_650_000,
            output_tokens=405_300,
        )
        self.assertEqual(self.mod.token_triplet_text(usage), "95.2M/92.7M/405K")
        self.assertLessEqual(self.mod.display_width(self.mod.token_triplet_text(usage)), 18)

    def test_v162_narrow_wide_uses_continuation_layout(self):
        headers, widths, _, inline = self.mod.summary_table_layout(100, True)
        self.assertFalse(inline)
        self.assertNotIn("TOKENS I/C/O", headers)
        self.assertLessEqual(sum(widths) + 2 * (len(widths) - 1), 100)

'''
t = replace_once(t, "\n\nif __name__ == \"__main__\":\n", "\n" + insert + "\nif __name__ == \"__main__\":\n", "v162 tests")
tests.write_text(t, encoding="utf-8")


readme = Path("README.md")
r = readme.read_text(encoding="utf-8")
section = '''## v1.6.2: readable project-aware wide summaries

v1.6.2 rebalances the 144-cell summary after project-aware labels made the old `--wide` SESSION column too narrow. At the canonical report width, SESSION now receives **34 cells** and INPUT/CACHED/OUTPUT are packed into one `TOKENS I/C/O` column such as `95.2M/92.7M/405K`. Long `[project] title` labels shorten the project tag first and reserve space for the actual Codex name/title, so a row no longer degrades to only `[atomic-cross-mod…]`.

On narrower terminals, `--wide` keeps the normal readable summary and places the token triplet on an indented continuation line rather than forcing the project/session label into an unusable width. The report still respects the 144-cell cap and all accounting, Fast attribution, and weekly calibration semantics are unchanged.

'''
r = replace_once(r, "# codex-usage\n\n", "# codex-usage\n\n" + section, "README section")
readme.write_text(r, encoding="utf-8")


zh = Path("README.zh-CN.md")
z = zh.read_text(encoding="utf-8")
zh_section = '''## v1.6.2：加宽可读的 project-aware SESSION

v1.6.2 重新平衡 144-cell 摘要布局。加入 project 前缀后，旧 `--wide` 模式的 SESSION 只有约 18 格，往往只能看到 `[atomic-cross-mod…]`。现在全宽报告会给 SESSION **34 格**，并把 INPUT/CACHED/OUTPUT 合并为紧凑的 `TOKENS I/C/O`，例如 `95.2M/92.7M/405K`。

当 `[project] session name/title` 仍然过长时，会优先缩短 project tag，并为真正的 Codex session 名或标题保留空间。较窄终端中，`--wide` 会把 token 三元组放到下一条缩进行，而不是继续挤压 SESSION。144-cell 上限、Fast 统计、weekly 估算和 credit 计算均未改变，也不需要重建 cache。

'''
z = replace_once(z, "# codex-usage\n\n", "# codex-usage\n\n" + zh_section, "Chinese README section")
zh.write_text(z, encoding="utf-8")


changelog = Path("CHANGELOG.md")
c = changelog.read_text(encoding="utf-8")
entry = '''## 1.6.2 — 2026-09-01

- Rebalanced the capped 144-cell `--wide` summary so SESSION receives 34 cells instead of roughly 18.
- Packed INPUT/CACHED/OUTPUT into a compact `TOKENS I/C/O` triplet, preserving all three diagnostics with much less horizontal cost.
- Added project-aware session-cell fitting that shortens a long project tag first and reserves visible space for the Codex name/title.
- Added a narrow-terminal `--wide` fallback that emits token continuation lines instead of wrapping or crushing the SESSION label.
- Kept accounting, tier attribution, weekly calibration, cache schema, and detail-table right edges unchanged.

'''
c = replace_once(c, "# Changelog\n\n", "# Changelog\n\n" + entry, "changelog entry")
changelog.write_text(c, encoding="utf-8")
