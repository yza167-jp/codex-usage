def _terminal_label(value: object) -> str:
    """Sanitize untrusted metadata only at the terminal boundary."""
    return _clean_thread_label(re.sub(r"[\x00-\x1f\x7f-\x9f]", "", str(value or "")))


def cloud_models(row: dict) -> List[str]:
    """Use only explicit backend model IDs; never price Cloud lifetime groups."""
    return model_names(g["model"] for g in row.get("groups", [])
                       if isinstance(g, dict) and isinstance(g.get("model"), str) and g["model"])


def cloud_value(row: dict, key: str) -> Optional[float]:
    if row.get("data_status") == "unavailable":
        return None
    return _cloud_amount(row.get(key))


def cloud_value_text(row: dict, key: str, percent: bool = False) -> str:
    value = cloud_value(row, key)
    if value is None:
        return "—"
    # Keep small real nonzero values distinguishable from zero.
    number = "<0.0001" if 0 < value < 0.0001 else f"{value:.4f}"
    return number + ("%" if percent else "")


def join_session_views(local_items: Iterable[dict], cloud_report: dict) -> List[dict]:
    """One identity per exact root thread ID, with two *separate* measurements.

    The local payload is opaque to this join (a render tuple or export record).
    Names/projects never serve as join keys. A Cloud thread already included in
    a local parent's rollup stays its own lifetime row; it is not added again.
    Sorting by metadata, not unlike-scope usage amounts, keeps the unified list
    from posing as a combined period ranking.
    """
    entries: Dict[object, dict] = {}
    parents: Dict[str, str] = {}
    for item in local_items:
        sid = item["session_id"]
        entries[sid] = dict(item, cloud=None, sources=["local"], local_rollup_parent=None)
        for child in item.get("source_ids", []):
            if child != sid:
                parents[child] = sid
    for position, cloud in enumerate(cloud_report.get("sessions", [])):
        sid = cloud.get("session_id")
        key = sid if sid else ("anonymous_cloud", position)
        if key in entries:
            entries[key]["cloud"] = cloud
            if "cloud" not in entries[key]["sources"]:
                entries[key]["sources"].append("cloud")
            if not entries[key].get("project_name"):
                entries[key]["project_name"] = cloud.get("project_name") or _cwd_project_label(cloud.get("cwd"))
        else:
            entries[key] = {
                "session_id": sid, "title": cloud.get("title") or sid or "Unnamed Cloud session",
                "project_name": cloud.get("project_name") or _cwd_project_label(cloud.get("cwd")),
                "local": None, "cloud": cloud, "sources": ["cloud"],
                "local_rollup_parent": parents.get(sid),
            }
    def order(entry):
        cloud = entry["cloud"] or {}
        has_data = entry["local"] is not None or any(
            cloud_value(cloud, key) is not None
            for key in ("weekly_limit_percent", "five_hour_limit_percent", "balance_usage_credits")
        )
        return (not has_data, _terminal_label(entry.get("project_name")).casefold() or "\uffff",
                _terminal_label(entry["title"]).casefold(), str(entry["session_id"] or ""))
    return sorted(entries.values(), key=order)


def _unified_layout(width: int) -> Tuple[List[str], List[int], int]:
    # Weekly period and lifetime columns are deliberately distinct. Secondary
    # token/cache/share diagnostics live on --wide continuation lines.
    gap = 2 if width >= 132 else 1
    if width >= 116:
        headers = ["PROJECT", "SESSION", "SRC", "PERIOD≈", "LIFE %", "MODEL(S)", "TIER(S)", "1H≈", "CREDITS*", "STATE/DATA"]
        widths = shrink_widths_to_target(
            [18, 34, 5, 9, 9, 12, 9, 8, 9, 13],
            [10, 24, 5, 9, 9, 8, 5, 8, 9, 11], width,
            (0, 5, 6, 1, 9), gap=gap,
        )
    else:
        headers = ["PROJECT", "SESSION", "SRC", "PERIOD≈", "LIFE %", "STATE/DATA"]
        widths = shrink_widths_to_target(
            [18, 34, 5, 10, 10, 13], [8, 20, 5, 9, 9, 11], width,
            (0, 1, 3, 4, 5), gap=gap,
        )
    widths = fit_widths_to_target(widths, width, (1,), gap=gap)
    return headers, widths, gap


def render_unified_summary(
    entries: List[dict], report: dict, period_label: str, width: int,
    color: Colorizer, calibration: Optional[QuotaCalibration], wide: bool,
    include_local: bool = True,
) -> List[str]:
    headers, widths, gap = _unified_layout(width)
    numeric = {i for i, h in enumerate(headers) if h in ("PERIOD≈", "LIFE %", "1H≈", "CREDITS*")}
    def line(values, heading=False, emphasis=None):
        cells = []
        for i, (value, w) in enumerate(zip(values, widths)):
            cell = pad_display(_terminal_label(value), w, right=i in numeric)
            if heading:
                cell = color.wrap(cell, color.BOLD, color.CYAN)
            elif headers[i] == "SRC":
                cell = color.wrap(cell, color.CYAN if value == "LOCAL" else color.MAGENTA)
            elif headers[i] in ("SESSION", "STATE/DATA") and emphasis:
                cell = color.wrap(cell, emphasis)
            cells.append(cell)
        return (" " * gap).join(cells)
    def note(text):
        return [color.wrap(part, color.DIM) for part in wrap_display_words(_terminal_label(text), width)]
    lines = note("Sessions — local and Cloud together; ordered by project/name, missing-data-only entries last.")
    lines += note(f"PERIOD≈ = local weekly equivalent for {period_label}; LIFE % = Cloud lifetime weekly amount (not current week).")
    lines += note("Cloud Data as of: " + (report.get("data_as_of") or "unavailable"))
    separator = (" " * gap).join("-" * w for w in widths)
    lines += ["", line(headers, heading=True), color.wrap(separator, color.DIM)]
    local_rows = [e["local"] for e in entries if e["local"] is not None]
    known_total = sum(row[2] for row in local_rows if row[2] is not None)
    for entry in entries:
        row, cloud = entry["local"], entry["cloud"]
        source = "BOTH" if len(entry["sources"]) == 2 else entry["sources"][0].upper()
        values = {h: "—" for h in headers}
        values.update(PROJECT=entry.get("project_name") or "—", SESSION=entry["title"], SRC=source)
        extras = []
        emphasis = None
        if row is not None:
            b, u, credits, complete, cache, state, health, burn, _, burn_complete, orphan = row
            values["SESSION"] += f" (+{len(b.child_sessions)} sub)" if b.child_sessions else ""
            values["PERIOD≈"] = weekly_percent_text(credits, calibration, complete)
            values["1H≈"] = weekly_percent_text(burn if burn is not None and burn > 0 else None, calibration, burn_complete)
            values["CREDITS*"] = "—" if credits is None else f"{credits:.1f}" + ("" if complete else "+")
            values["TIER(S)"] = tier_label(b.usage_by_model.keys())
            values["STATE/DATA"] = status_text(state, health, orphan)
            models = list(b.usage_by_model)
            emphasis = (color.RED if health == "ROTATE" else color.YELLOW if health == "WATCH"
                        else color.GREEN if state == "ACTIVE" else color.CYAN if state == "RECENT" else None)
            if wide:
                share = f"{100 * credits / known_total:.1f}%" if credits is not None and known_total > 0 else "—"
                extras.append(f"TOKENS I/C/O {token_triplet_text(u)} · CACHE TAX {cache:.1f} · LOCAL SHARE {share}")
        else:
            models = cloud_models(cloud or {})
            values["STATE/DATA"] = (cloud or {}).get("data_status") or "unavailable"
        if cloud is not None:
            values["LIFE %"] = cloud_value_text(cloud, "weekly_limit_percent", percent=True)
            if row is not None:
                extras.append("Cloud lifetime data: " + str(cloud.get("data_status") or "unavailable"))
            if wide:
                extras.append("Cloud lifetime 5H % " + cloud_value_text(cloud, "five_hour_limit_percent", True)
                              + " · BALANCE CREDITS " + cloud_value_text(cloud, "balance_usage_credits"))
        # Models may be absent from backend groups; do not invent one from the title.
        models = [_terminal_label(model) for model in model_names(models)]
        if "MODEL(S)" in headers:
            i = headers.index("MODEL(S)")
            model, continuation = model_cell_layout(models, widths[i], width) if models else ("—", [])
            values["MODEL(S)"] = model
        else:
            continuation = []
            if models:
                extras.insert(0, "Models: " + model_label(models) + (" · TIER " + values.get("TIER(S)", "—") if row is not None else ""))
            if row is not None:
                extras.append("1H≈ " + values["1H≈"] + " · CREDITS* " + values["CREDITS*"])
        if entry.get("local_rollup_parent"):
            extras.append("Local tokens already rolled into " + short_sid(entry["local_rollup_parent"]) + "; lifetime not added again.")
        lines.append(line([values[h] for h in headers], emphasis=emphasis))
        lines.extend(color.wrap(part, color.DIM) for part in continuation)
        for extra in extras:
            lines.extend(color.wrap("  " + part, color.DIM)
                         for part in wrap_display_words(_terminal_label(extra), width - 2))
    if not entries:
        lines.append("No local or Cloud sessions found." if include_local else "No Cloud sessions found.")
    if include_local:
        # Empty/no-price local totals stay unknown. Never fill them from Cloud.
        total = known_total if any(row[2] is not None for row in local_rows) else None
        burn = sum(row[7] for row in local_rows if row[7] is not None)
        complete = all(row[3] for row in local_rows)
        totals = {h: "" for h in headers}
        totals.update(PROJECT="LOCAL TOTAL", SRC="LOCAL", **{
            "PERIOD≈": weekly_percent_text(total, calibration, complete), "LIFE %": "—",
            "CREDITS*": "—" if total is None else f"{total:.1f}" + ("" if complete else "+"),
            "1H≈": weekly_percent_text(burn or None, calibration, all(row[9] for row in local_rows if row[7])),
        })
        lines += [color.wrap(separator, color.DIM), line([totals[h] for h in headers], heading=True)]
        if wide:
            usage = Usage()
            for row in local_rows:
                usage += row[1]
            lines.extend(color.wrap("  " + part, color.DIM) for part in wrap_display_words(
                "LOCAL TOTAL TOKENS I/C/O " + token_triplet_text(usage), width - 2))
    lines.append("")
    lines += note("No combined TOTAL: Cloud lifetime and local selected-period amounts may overlap and cannot be added.")
    lines += note("SRC is the telemetry source, not the executor location. BOTH joins an exact thread ID, not its usage amounts.")
    lines += note("Partial/unavailable data is not zero. Cloud token/time-window totals are unavailable; CREDITS* excludes Cloud balance credits.")
    lines += note("Local STATE/DATA shows activity/health; Cloud shows availability, not running status. '?' marks partial local WEEKLY estimates.")
    return lines


def render_cloud_detail(entry: dict, report: dict, width: int, color: Colorizer, heading: bool = True) -> List[str]:
    cloud = entry["cloud"]
    lines: List[str] = []
    def add(text):
        lines.extend(wrap_display_words(_terminal_label(text), width))
    if heading:
        lines += ["", color.wrap("=" * width, color.BLUE)]
        lines.append(color.wrap("DETAILS  " + truncate(_terminal_label(entry["title"]), width - 9), color.BOLD, color.CYAN))
        add("session: " + str(entry["session_id"] or "unavailable"))
        add("project: " + str(entry.get("project_name") or "—"))
    lines.append(color.wrap("Cloud lifetime usage — backend amounts, not selected-period usage", color.BOLD, color.MAGENTA))
    add("data: " + str(cloud.get("data_status") or "unavailable")
        + " · Data as of: " + str(report.get("data_as_of") or "unavailable"))
    add("LIFE WEEKLY % " + cloud_value_text(cloud, "weekly_limit_percent", True)
        + " · LIFE 5H % " + cloud_value_text(cloud, "five_hour_limit_percent", True)
        + " · BALANCE CREDITS " + cloud_value_text(cloud, "balance_usage_credits"))
    if cloud.get("title") and cloud["title"] != entry["title"]:
        add("Cloud title: " + str(cloud["title"]))
    if cloud.get("cwd"):
        add("Cloud cwd: " + str(cloud["cwd"]))
    models = cloud_models(cloud)
    if models:
        add("Cloud models: " + model_label(models))
    if entry.get("local_rollup_parent"):
        add("Local tokens already rolled into " + entry["local_rollup_parent"] + "; Cloud remains individual lifetime usage.")
    add("No Cloud period tokens, 1H burn or model credit breakdown available. Descendants are not rolled up.")
    return lines


def unified_json_sessions(local_report: dict, cloud_report: dict) -> List[dict]:
    items = [{"session_id": row["session_id"], "title": row["title"],
              "project_name": row.get("project_name"), "local": row,
              "source_ids": [agent["session_id"] for agent in row.get("agent_breakdown", [])]}
             for row in local_report["sessions"]]
    return [{"session_id": e["session_id"], "title": e["title"], "project_name": e.get("project_name") or None,
             "sources": e["sources"], "local_usage": e["local"], "cloud_usage": e["cloud"],
             "local_rollup_parent": e.get("local_rollup_parent"),
             "local_scope": "selected_period" if e["local"] is not None else None,
             "cloud_scope": "lifetime" if e["cloud"] is not None else None}
            for e in join_session_views(items, cloud_report)]


