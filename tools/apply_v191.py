from pathlib import Path

p = Path('codex-usage')
s = p.read_text(encoding='utf-8')
assert 'VERSION = "1.9.0"' in s
s = s.replace('VERSION = "1.9.0"', 'VERSION = "1.9.1"', 1)
s = s.replace('    quota_local_complete: bool = True,\n) -> str:\n', '    quota_local_complete: bool = True,\n    cloud_report: Optional[dict] = None,\n) -> str:\n', 1)
s = s.replace('    if not rows:\n        lines.append("No token_count usage found for this period.")', '    if not rows and cloud_report is None:\n        lines.append("No token_count usage found for this period.")', 1)
start = s.index('    lines.append(fmt_row(headers,')
end = s.index('    if details:\n        for b, total_u,', start)
summary = s[start:end]
s = s[:start] + '''    entries = None
    if cloud_report is not None:
        items = [{"session_id": r[0].session_id, "title": bucket_identity(r[0])[1],
                  "project_name": bucket_identity(r[0])[0], "local": r,
                  "source_ids": list(r[0].usage_by_source)} for r in rows]
        entries = join_session_views(items, cloud_report)
        lines.extend(render_unified_summary(entries, cloud_report, period_label,
                                           terminal_width, color, quota_calibration, wide))
    else:
''' + ''.join('    ' + line if line.strip() else line for line in summary.splitlines(True)) + s[end:]
s = s.replace('''    if details:
        for b, total_u, total_credits, total_complete, total_cache_tax, state, health, burn, recent_cache, burn_complete, is_orphan in rows:
''', '''    if details:
        detail_entries = entries if entries is not None else [{"local": row, "cloud": None} for row in rows]
        for entry in detail_entries:
            if entry["local"] is None:
                lines.extend(render_cloud_detail(entry, cloud_report or {}, terminal_width, color))
                continue
            b, total_u, total_credits, total_complete, total_cache_tax, state, health, burn, recent_cache, burn_complete, is_orphan = entry["local"]
''', 1)
s = s.replace('''            lines.append(f"Usage      WEEKLY≈ {usage_weekly} · CREDITS* {credit_mark}")
''', '''            scope_prefix = "Local selected-period" if cloud_report is not None else "Usage"
            lines.append(f"{scope_prefix}      WEEKLY≈ {usage_weekly} · CREDITS* {credit_mark}")
            if entry.get("cloud") is not None:
                lines.extend(render_cloud_detail(entry, cloud_report or {}, detail_width, color, heading=False))
''', 1)
helpers = Path('tools/v191_display_helpers.py').read_text(encoding='utf-8')
s = s.replace('def render_cloud_usage(report: dict, output: str = "table") -> str:', helpers + '''def render_cloud_usage(report: dict, output: str = "table", details: bool = False,
                       wide: bool = False, color: Optional[Colorizer] = None) -> str:''', 1)
start = s.index('    lines = ["Codex Cloud usage — lifetime')
end = s.index('\n\ndef append_cloud_csv(', start)
s = s[:start] + '''    color = color or Colorizer("never")
    width = max(80, min(REPORT_MAX_WIDTH, shutil.get_terminal_size(fallback=(120, 24)).columns))
    lines = [color.wrap("Codex usage — Cloud lifetime (dot / durable sessions)", color.BOLD, color.CYAN)]
    entries = join_session_views([], report)
    lines.extend(render_unified_summary(entries, report, "not available", width, color, None, wide, include_local=False))
    if details:
        for entry in entries:
            lines.extend(render_cloud_detail(entry, report, width, color))
    return "\\n".join(lines)
''' + s[end:]
s = s.replace('''    for row in local:
        writer.writerow({**row, "host": "local", "scope": "selected_period"})
    writer.writerows(cloud)
''', '''    local_rows = [{"session_id": row["session_id"], "title": row["title"],
                   "project_name": row.get("project_name"), "local": row} for row in local]
    for entry in join_session_views(local_rows, {"sessions": list(cloud)}):
        if entry["local"] is not None:
            writer.writerow({**entry["local"], "host": "local", "scope": "selected_period"})
        if entry["cloud"] is not None:
            writer.writerow(entry["cloud"])
''', 1)
s = s.replace('''            print(render_cloud_usage(cloud_report, "json" if args.json else "csv" if args.csv else "table"),
''', '''            print(render_cloud_usage(cloud_report, "json" if args.json else "csv" if args.csv else "table",
                                     details=args.details, wide=args.wide, color=Colorizer(args.color)),
''', 1)
s = s.replace('''            result["cloud_usage"] = cloud_report
''', '''            result["cloud_usage"] = cloud_report
            result["unified_sessions"] = unified_json_sessions(result, cloud_report)
            result["unified_session_order"] = "project_name_then_title_missing_data_last"
''', 1)
s = s.replace('''            quota_local_complete=quota_complete,
        ))
        if cloud_report is not None:
            print("\\n" + render_cloud_usage(cloud_report))
''', '''            quota_local_complete=quota_complete, cloud_report=cloud_report,
        ))
''', 1)
s = s.replace('''                        "archived": archived,
''', '''                        "archived": archived,
                        "cwd": row.get("cwd") if isinstance(row.get("cwd"), str) else None,
                        "project_name": row.get("projectName") if isinstance(row.get("projectName"), str) else None,
''', 1)
s = s.replace('''            "session_id": sid, "title": meta.get("title") or sid,
            "host": "cloud",''', '''            "session_id": sid, "title": meta.get("title") or sid,
            "project_name": meta.get("project_name") or _cwd_project_label(meta.get("cwd")) or None,
            "cwd": meta.get("cwd"),
            "host": "cloud",''', 1)
s = s.replace('fieldnames=fields + ["data_as_of"], extrasaction="ignore"', 'fieldnames=fields + ["data_as_of", "project_name", "cwd"], extrasaction="ignore"', 1)
s = s.replace('Also query dot/durable sessions and show backend lifetime usage separately (requires network and ChatGPT login).', 'Show local period and Cloud lifetime usage in one session table (requires network and ChatGPT login).')
p.write_text(s, encoding='utf-8')
p = Path('tests/test_codex_usage.py')
p.write_text(p.read_text(encoding='utf-8').replace('"1.9.0"', '"1.9.1"', 1), encoding='utf-8')
p = Path('tests/test_cloud_usage.py')
p.write_text(p.read_text(encoding='utf-8').replace('render_cloud_usage(report, "table")', 'render_cloud_usage(report, "table", details=True)', 1), encoding='utf-8')

sections = {
'README.md': '''## v1.9.1: one local / Cloud session list

`codex-usage 12h --cloud --details` now lists **all sessions before any details**,
in one PROJECT / SESSION table. Two weekly-first columns keep scopes explicit:
**PERIOD≈** is the selected local window's weekly-equivalent estimate;
**LIFE %** is the Cloud backend's lifetime weekly amount, not current-week usage.
**SRC** is LOCAL, CLOUD or BOTH (telemetry source, not the executor location).

An exact root thread ID appears once with both measurements. Matching names or
projects do not merge threads. Rows use project/name order, not a false ranking
of lifetime amounts against a 12h window; entries without any usage data stay
visible at the end. Only **LOCAL TOTAL** is computed. There is no combined
period or Cloud lifetime total, no extra Cloud rollup, and no double charge for
matching IDs. Cloud records may include Mac execution.

`--details` follows the same inventory order. A shared thread has one detail
section containing separately labeled local/Cloud amounts; Cloud-only entries
show lifetime weekly/5h, balance credits, availability and freshness without
empty token tables. `--wide` moves token/cache/share and Cloud balance diagnostics
to continuation lines. At 144 cells PROJECT/SESSION retain 18/34 cells; smaller
terminals move model/tier/credit diagnostics below each row.

Cloud-only `cloud` uses the same layout and honors `--details` / `--wide` / color.
JSON retains `sessions` and `cloud_usage`, adding `unified_sessions` with separate
measurement objects. CSV retains two measurement rows for a shared ID, now
adjacent, with explicit host/scope and separate amount columns; Cloud metadata
columns are additive. Normal local commands remain offline and unchanged.

**No cache rebuild or new flag:** keep using `--cloud` explicitly. Network
requests, rate cards, quota calibration and raw accounting are unchanged.
See [display, scopes and compatibility](docs/v1.9.1-unified-sessions.md).

''',
'README.zh-CN.md': '''## v1.9.1：Cloud / Local 会话统一显示

`codex-usage 12h --cloud --details` 现在先在**同一张表里显示全部会话**，再进入
详情，不再把 Cloud 区块放在全部 Local 详情之后。保留 PROJECT / SESSION 分列：
**PERIOD≈** 表示所选时段的本地 weekly 估算，**LIFE %** 表示服务端 Cloud 的
lifetime weekly 用量，**不是本周或过去 12 小时的扣减**。SRC 为 LOCAL / CLOUD /
BOTH，表示数据来源，不是工具执行位置。

仅同一 thread ID 合并展示为一个条目，两种测量仍分别保留；同名、同项目不合并。
按项目与会话名排序，无用量数据的条目排在最后，不能按 lifetime 与 12h 数字混排
成消耗榜。合计明确标为 **LOCAL TOTAL**，不把 Cloud 累计用量相加，也不对 Cloud
子线程额外汇总。Cloud 会话可能包含 Mac 执行，不能按来源相加当作去重。

详情顺序与摘要一致。同 ID 的本地详情中同时显示 Cloud 累计用量；纯 Cloud
详情只展示 weekly/5h、余额 credits、数据状态和更新时间，不生成空 token 表。
`--wide` 的 token/cache/share 和 Cloud 余额信息放在续行；保持 144 格上限，
PROJECT / SESSION 在全宽下各 18 / 34 格。窄终端会把次要字段移到续行。

`cloud` 单独查询也使用同一布局，支持 `--details`、`--wide` 和配色。JSON 保留
旧字段，新增按会话组织的 `unified_sessions`；CSV 对同 ID 的两种测量保留相邻
的两行，并保留 host/scope 和分开的金额列，Cloud 元信息列仅追加。

**不用重建 cache，也没有新必需参数。** 仍需显式使用 `--cloud` 才联网；本地默认
命令、计价、Fast、quota 校准、Cloud 查询接口与请求次数均不改变。
详见[统一显示与计量范围说明](docs/v1.9.1-unified-sessions.md)。

'''}
for filename, section in sections.items():
    p = Path(filename)
    p.write_text(p.read_text(encoding='utf-8').replace('# codex-usage\n\n', '# codex-usage\n\n' + section, 1), encoding='utf-8')
p = Path('README.md')
p.write_text(p.read_text(encoding='utf-8').replace('Local window report plus separate Cloud lifetime usage', 'Unified session table with separate period/lifetime amounts'), encoding='utf-8')
p = Path('docs/v1.9.0-cloud-usage.md')
p.write_text(p.read_text(encoding='utf-8').replace('# v1.9.0: durable / dot usage\n', '# v1.9.0: durable / dot usage\n\nDisplay update: v1.9.1 replaces the appended terminal section with a [unified\nsession inventory](v1.9.1-unified-sessions.md). The data scope, interfaces and\nauthentication rules described below are unchanged.\n', 1), encoding='utf-8')
p = Path('CHANGELOG.md')
p.write_text(p.read_text(encoding='utf-8').replace('# Changelog\n\n', '''# Changelog

## 1.9.1 — 2026-10-18

- Replace the appended Cloud table with a single source-aware local/Cloud inventory before details; preserve distinct PERIOD≈ and lifetime LIFE % columns.
- Match only exact root thread IDs, retain both measurements, and annotate Cloud threads whose local tokens are already rolled into a parent. Do not add lifetime, local totals or balance credits together.
- Sort the unified inventory by project/name, with missing-data-only entries last. LOCAL TOTAL remains a local selected-period subtotal, not an account-wide total.
- Reuse the inventory order for details; Cloud-only details retain lifetime amounts, availability and freshness without empty token breakdowns. Preserve 144-cell/CJK/color layout and useful wide diagnostics.
- Preserve existing JSON objects and CSV fields, adding unified_sessions to combined JSON and optional Cloud metadata to CSV. Shared-ID CSV measurements are adjacent but remain separate host/scope rows.
- Keep explicit Cloud opt-in, read-only network/auth behavior, raw accounting, rates and cache schemas unchanged. No cache rebuild.
- Add unified-view regression coverage for scope separation, exact-ID matching, rollups, missing/zero values, model display, color/CJK/widths, exports and CLI compatibility.

''', 1), encoding='utf-8')
