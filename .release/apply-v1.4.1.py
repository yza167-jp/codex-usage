from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)


p = Path("codex-usage")
s = p.read_text(encoding="utf-8")
s = replace_once(s, 'import sqlite3\nimport sys\nimport time\n', 'import sqlite3\nimport sys\nimport time\nimport shutil\n', 'import shutil')
s = replace_once(s, 'VERSION = "1.4.0"', 'VERSION = "1.4.1"', 'version')
old = '''def _tz_label(tz) -> str:\n    if tz is not None:\n        return getattr(tz, "key", None) or str(tz)\n    local = datetime.now().astimezone()\n    return local.tzname() or "local"\n\n\n'''
new = old + '''def _tz_display(tz, now: datetime) -> str:\n    """Human-readable zone label with an unambiguous UTC offset."""\n    label = _tz_label(tz)\n    current = now.astimezone(tz) if tz is not None else now.astimezone()\n    off = current.utcoffset()\n    if off is None:\n        return label\n    total = int(off.total_seconds())\n    sign = "+" if total >= 0 else "-"\n    total = abs(total)\n    hours, rem = divmod(total, 3600)\n    minutes = rem // 60\n    return f"{label} (UTC{sign}{hours:02d}:{minutes:02d})"\n\n\n'''
s = replace_once(s, old, new, 'timezone display helper')
s = replace_once(s, '    tzname = _tz_label(tz)\n', '    tzname = _tz_display(tz, now)\n', 'timezone display use')
old = '''    if wide:\n        headers = ["SESSION", "MODEL(S)", "INPUT", "CACHED", "OUTPUT", "CREDITS*", "CACHE TAX", "1H BURN", "SHARE", "STATUS"]\n        widths = [36, 18, 9, 9, 9, 10, 10, 9, 7, 13]\n        align_right = {2, 3, 4, 5, 6, 7, 8}\n    else:\n        headers = ["SESSION", "MODEL(S)", "CREDITS*", "CACHE TAX", "1H BURN", "SHARE", "STATUS"]\n        widths = [38, 20, 10, 10, 9, 7, 13]\n        align_right = {2, 3, 4, 5}\n'''
new = '''    terminal_width = max(80, shutil.get_terminal_size(fallback=(120, 24)).columns)\n    gap = 2\n    if wide:\n        headers = ["SESSION", "MODEL(S)", "INPUT", "CACHED", "OUTPUT", "CREDITS*", "CACHE TAX", "1H BURN", "SHARE", "STATUS"]\n        fixed = [9, 9, 9, 10, 10, 9, 7, 13]\n        fixed_total = sum(fixed) + gap * (len(headers) - 1)\n        flexible = max(28, terminal_width - fixed_total)\n        model_w = max(14, min(24, flexible // 3))\n        session_w = max(18, flexible - model_w)\n        widths = [session_w, model_w] + fixed\n        align_right = {2, 3, 4, 5, 6, 7, 8}\n    else:\n        headers = ["SESSION", "MODEL(S)", "CREDITS*", "CACHE TAX", "1H BURN", "SHARE", "STATUS"]\n        fixed = [10, 10, 9, 7, 13]\n        fixed_total = sum(fixed) + gap * (len(headers) - 1)\n        flexible = max(30, terminal_width - fixed_total)\n        model_w = max(14, min(24, flexible // 3))\n        session_w = max(20, flexible - model_w)\n        widths = [session_w, model_w] + fixed\n        align_right = {2, 3, 4, 5}\n'''
s = replace_once(s, old, new, 'adaptive summary widths')
old = '''        if is_orphan:\n            styles[status_idx] = "orphan"\n            styles[title_idx] = "orphan"\n        elif state == "ACTIVE":\n            styles[title_idx] = "active"\n        elif state == "RECENT":\n            styles[title_idx] = "recent"\n        else:\n            styles[title_idx] = "idle"\n'''
new = '''        if is_orphan:\n            styles[status_idx] = "orphan"\n            styles[title_idx] = "orphan"\n        elif state in ("ACTIVE", "RECENT") and health == "ROTATE":\n            styles[title_idx] = "rotate"\n        elif state in ("ACTIVE", "RECENT") and health == "WATCH":\n            styles[title_idx] = "watch"\n        elif state in ("ACTIVE", "RECENT") and health == "OK":\n            styles[title_idx] = "ok" if state == "ACTIVE" else "recent"\n        else:\n            styles[title_idx] = "idle"\n'''
s = replace_once(s, old, new, 'health-aware title color')
old = '''            lines.append("")\n            lines.append(color.wrap("=" * 104, color.BLUE))\n            title_style = (color.BOLD, color.GREEN) if state == "ACTIVE" else (color.BOLD, color.CYAN)\n            if is_orphan:\n                title_style = (color.BOLD, color.MAGENTA)\n            lines.append(color.wrap(b.title, *title_style))\n            lines.append(f"session: {b.session_id}")\n            if b.cwd:\n                lines.append(f"cwd: {b.cwd}")\n            if b.child_sessions:\n                lines.append(f"rolled-up subagents: {len(b.child_sessions)}")\n            if is_orphan:\n                lines.append(color.wrap(\n                    "lineage: ORPHAN SUBAGENT (parent unavailable/unresolved locally)",\n                    color.BOLD, color.MAGENTA,\n                ))\n\n            lines.append(\n                f"state: {styled_cell(state, 'active' if state == 'ACTIVE' else 'recent' if state == 'RECENT' else 'idle').strip()}  "\n                f"last activity: {human_age(b.last_activity, now)} ago"\n            )\n            if health != "—":\n                hstyle = "rotate" if health == "ROTATE" else "watch" if health == "WATCH" else "ok"\n                lines.append(f"thread health: {styled_cell(health, hstyle).strip()}")\n            else:\n                lines.append("thread health: —")\n\n            if burn is not None and burn > 0:\n                projection = burn * 2.0\n                lines.append(\n                    f"trailing 1h burn: {burn:.1f} credits "\n                    f"(cache {recent_cache:.1f}); "\n                    + (f"simple +2h projection: ≈{projection:.1f}" if state == "ACTIVE" else "projection: —")\n                )\n            lines.append("")\n'''
new = '''            lines.append("")\n            detail_width = max(72, min(120, terminal_width))\n            lines.append(color.wrap("=" * detail_width, color.BLUE))\n            if is_orphan:\n                title_style = (color.BOLD, color.MAGENTA)\n            elif health == "ROTATE" and state in ("ACTIVE", "RECENT"):\n                title_style = (color.BOLD, color.RED)\n            elif health == "WATCH" and state in ("ACTIVE", "RECENT"):\n                title_style = (color.BOLD, color.YELLOW)\n            elif health == "OK" and state == "ACTIVE":\n                title_style = (color.BOLD, color.GREEN)\n            else:\n                title_style = (color.BOLD, color.CYAN) if state == "RECENT" else (color.DIM,)\n            short_title = truncate(b.title, max(30, detail_width - 9))\n            lines.append(color.wrap(f"DETAILS  {short_title}", *title_style))\n            lines.append(f"session: {b.session_id}")\n            if b.cwd:\n                lines.append(f"cwd: {b.cwd}")\n            if b.child_sessions:\n                lines.append(f"subagents in window: {len(b.child_sessions)}")\n            if is_orphan:\n                lines.append(color.wrap(\n                    "lineage: ORPHAN SUBAGENT (parent unavailable/unresolved locally)",\n                    color.BOLD, color.MAGENTA,\n                ))\n\n            state_style = 'active' if state == 'ACTIVE' else 'recent' if state == 'RECENT' else 'idle'\n            state_text = styled_cell(state, state_style).strip()\n            health_text = "—"\n            if health != "—":\n                hstyle = "rotate" if health == "ROTATE" else "watch" if health == "WATCH" else "ok"\n                health_text = styled_cell(health, hstyle).strip()\n            lines.append(f"{state_text} · last {human_age(b.last_activity, now)} · health {health_text}")\n\n            if burn is not None and burn > 0:\n                projection = burn * 2.0\n                projection_text = f" · +2h ≈{projection:.1f}" if state == "ACTIVE" else ""\n                lines.append(f"1H BURN {burn:.1f} · cache {recent_cache:.1f}{projection_text}")\n            lines.append("")\n'''
s = replace_once(s, old, new, 'compact details')
p.write_text(s, encoding="utf-8")

p = Path("tests/test_codex_usage.py")
s = p.read_text(encoding="utf-8")
s = replace_once(s, 'self.assertIn("1.4.0", proc.stdout)', 'self.assertIn("1.4.1", proc.stdout)', 'version test')
p.write_text(s, encoding="utf-8")

p = Path("README.md")
s = p.read_text(encoding="utf-8")
needle = 'The core tool is a single Python script with **no mandatory third-party dependencies**. **v1.4.0 adds native Windows support** alongside macOS and Linux.\n'
s = replace_once(s, needle, needle + '\n**v1.4.1** is a terminal-UX polish release: health-aware session colors, adaptive column widths, compact detail headers, and unambiguous timezone labels.\n', 'English README')
p.write_text(s, encoding="utf-8")

p = Path("README.zh-CN.md")
s = p.read_text(encoding="utf-8")
needle = '核心工具仍然只有一个 Python 脚本，**正常使用零强制第三方依赖**。**v1.4.0 正式增加原生 Windows 支持**，同时保留 macOS 和 Linux 支持。\n'
s = replace_once(s, needle, needle + '\n**v1.4.1** 是一次终端 UX polish：按 health 着色 session、动态列宽、紧凑详情标题，以及不歧义的时区显示。\n', 'Chinese README')
p.write_text(s, encoding="utf-8")
