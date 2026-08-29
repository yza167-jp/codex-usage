from __future__ import annotations

import re
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing replacement anchor: {label}")
    return text.replace(old, new, 1)


def replace_regex(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL | re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"expected one regex replacement for {label}, got {count}")
    return updated


script_path = Path("codex-usage")
s = script_path.read_text(encoding="utf-8")
s = replace_once(s, 'VERSION = "1.6.0"', 'VERSION = "1.6.1"', "version")

s = replace_once(
    s,
    '''class Bucket:
    session_id: str
    title: str = ""
    cwd: str = ""
    source: str = ""
''',
    '''class Bucket:
    session_id: str
    title: str = ""
    cwd: str = ""
    source: str = ""
    session_name: str = ""
    thread_title: str = ""
    project_id: str = ""
    project_name: str = ""
''',
    "bucket metadata fields",
)

thread_index_block = r'''def _clean_thread_label(value: object) -> str:
    return " ".join(str(value or "").split())


def _cwd_project_label(raw_cwd: object) -> str:
    cwd = str(raw_cwd or "").strip()
    if not cwd:
        return ""
    try:
        leaf = Path(cwd).expanduser().name
    except (OSError, ValueError):
        leaf = ""
    return _clean_thread_label(leaf)


def _git_origin_project_label(raw_url: object) -> str:
    value = str(raw_url or "").strip().rstrip("/")
    if not value:
        return ""
    tail = value.rsplit("/", 1)[-1]
    if ":" in tail and "/" not in value:
        tail = tail.rsplit(":", 1)[-1]
    if tail.endswith(".git"):
        tail = tail[:-4]
    return _clean_thread_label(tail)


def _path_is_within(cwd: str, root: str) -> bool:
    try:
        cwd_norm = os.path.normcase(os.path.abspath(os.path.expanduser(cwd)))
        root_norm = os.path.normcase(os.path.abspath(os.path.expanduser(root)))
        return os.path.commonpath((cwd_norm, root_norm)) == root_norm
    except (OSError, ValueError):
        return False


def load_thread_index(codex_home: Path) -> Dict[str, dict]:
    """Best-effort read of Codex thread names, projects, titles, and cwd.

    Current Codex state databases distinguish an explicit user-facing thread
    ``name`` from the generated ``title``/``preview`` and may assign a thread to
    a named project. Older schemas remain supported through dynamic column and
    table discovery.
    """
    db = codex_home / "state_5.sqlite"
    if not db.exists():
        return {}

    result: Dict[str, dict] = {}
    try:
        conn = sqlite3.connect(_sqlite_ro_uri(db), uri=True, timeout=1.0)
    except (sqlite3.Error, OSError):
        return {}

    try:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "threads" not in tables:
            return {}
        cols = [str(row[1]) for row in conn.execute("PRAGMA table_info(threads)")]
        if "id" not in cols:
            return {}
        wanted = [
            c for c in (
                "id", "name", "title", "preview", "first_user_message",
                "project_id", "cwd", "source", "thread_source", "agent_nickname",
                "agent_role", "model_provider", "created_at", "updated_at",
                "rollout_path", "git_origin_url", "git_branch",
            ) if c in cols
        ]

        project_names: Dict[str, str] = {}
        if "projects" in tables:
            project_cols = {
                str(row[1]) for row in conn.execute("PRAGMA table_info(projects)")
            }
            if {"id", "name"}.issubset(project_cols):
                for project_id, project_name in conn.execute("SELECT id,name FROM projects"):
                    pid = str(project_id or "")
                    name = _clean_thread_label(project_name)
                    if pid and name:
                        project_names[pid] = name

        project_roots: List[Tuple[str, str, str]] = []
        if "project_roots" in tables and project_names:
            root_cols = {
                str(row[1]) for row in conn.execute("PRAGMA table_info(project_roots)")
            }
            if {"project_id", "path"}.issubset(root_cols):
                for project_id, root_path in conn.execute(
                    "SELECT project_id,path FROM project_roots"
                ):
                    pid = str(project_id or "")
                    root = str(root_path or "").strip()
                    name = project_names.get(pid, "")
                    if pid and root and name:
                        project_roots.append((pid, name, root))
                project_roots.sort(key=lambda item: len(item[2]), reverse=True)

        q = "SELECT " + ", ".join(
            '"' + c.replace('"', '""') + '"' for c in wanted
        ) + ' FROM "threads"'
        for row in conn.execute(q):
            item = dict(zip(wanted, row))
            sid = str(item.get("id") or "")
            if not sid:
                continue
            project_id = str(item.get("project_id") or "")
            project_name = project_names.get(project_id, "")
            if not project_name:
                cwd = str(item.get("cwd") or "")
                for inferred_id, inferred_name, root in project_roots:
                    if _path_is_within(cwd, root):
                        project_id = inferred_id
                        project_name = inferred_name
                        break
            item["project_id"] = project_id
            item["project_name"] = project_name
            result[sid] = item
    except sqlite3.Error:
        pass
    finally:
        conn.close()
    return result


def session_label_metadata(session: RawSession, index: Dict[str, dict]) -> Dict[str, str]:
    dbrow = index.get(session.session_id, {})
    explicit_name = _clean_thread_label(dbrow.get("name"))
    preview = _clean_thread_label(dbrow.get("preview"))
    generated_title = _clean_thread_label(dbrow.get("title"))
    first_user_message = _clean_thread_label(dbrow.get("first_user_message"))
    agent_nickname = _clean_thread_label(dbrow.get("agent_nickname"))
    agent_role = _clean_thread_label(dbrow.get("agent_role"))

    if session.is_subagent() and not explicit_name:
        if agent_nickname and agent_role:
            explicit_name = f"{agent_nickname} ({agent_role})"
        else:
            explicit_name = agent_nickname or agent_role

    thread_title = preview or generated_title or first_user_message
    base = explicit_name or thread_title

    project_id = str(dbrow.get("project_id") or "")
    project_name = _clean_thread_label(dbrow.get("project_name"))
    cwd = str(dbrow.get("cwd") or session.cwd or "").strip()
    repo_name = _git_origin_project_label(dbrow.get("git_origin_url"))
    context = project_name or repo_name or _cwd_project_label(cwd)

    if not base:
        base = context or session.session_id[:12]
        context = ""

    normalized_base = base.casefold().strip()
    normalized_context = context.casefold().strip()
    already_contextualized = bool(
        context
        and (
            normalized_base == normalized_context
            or normalized_base.startswith(f"[{normalized_context}]")
            or normalized_base.startswith(normalized_context + " ·")
            or normalized_base.startswith(normalized_context + ":")
        )
    )
    display_title = (
        f"[{context}] {base}" if context and not already_contextualized else base
    )
    return {
        "display_title": display_title,
        "session_name": explicit_name,
        "thread_title": thread_title,
        "project_id": project_id,
        "project_name": project_name or context,
        "cwd": cwd,
    }


def session_title(session: RawSession, index: Dict[str, dict]) -> str:
    return session_label_metadata(session, index)["display_title"]


def _disambiguate_bucket_titles(buckets: Dict[str, Bucket]) -> None:
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

s = replace_regex(
    s,
    r'def load_thread_index\(codex_home: Path\) -> Dict\[str, dict\]:.*?\n\ndef get_tz',
    thread_index_block + '\n\ndef get_tz',
    "thread index and label functions",
)

s = replace_once(
    s,
    '''        if bucket is None:
            dbrow = index.get(target_id, {})
            title = session_title(target_session, index)
''',
    '''        if bucket is None:
            dbrow = index.get(target_id, {})
            label_meta = session_label_metadata(target_session, index)
            title = label_meta["display_title"]
''',
    "bucket label metadata",
)

s = replace_once(
    s,
    '''            bucket = Bucket(
                session_id=target_id,
                title=title,
                cwd=str(dbrow.get("cwd") or target_session.cwd or ""),
                source=str(dbrow.get("source") or target_session.source or ""),
            )
''',
    '''            bucket = Bucket(
                session_id=target_id,
                title=title,
                cwd=str(dbrow.get("cwd") or target_session.cwd or ""),
                source=str(dbrow.get("source") or target_session.source or ""),
                session_name=label_meta["session_name"],
                thread_title=label_meta["thread_title"],
                project_id=label_meta["project_id"],
                project_name=label_meta["project_name"],
            )
''',
    "bucket metadata assignment",
)

s = replace_once(
    s,
    '''    return {sid: b for sid, b in buckets.items() if b.total_usage().nonzero()}


def render_table''',
    '''    visible = {sid: b for sid, b in buckets.items() if b.total_usage().nonzero()}
    _disambiguate_bucket_titles(visible)
    return visible


def render_table''',
    "visible bucket disambiguation",
)

s = replace_once(
    s,
    '''            lines.append(f"session: {b.session_id}")
            if b.cwd:
                lines.append(f"cwd: {b.cwd}")
''',
    '''            lines.append(f"session: {b.session_id}")
            if b.project_name:
                lines.append(f"project: {b.project_name}")
            if b.session_name:
                lines.append(f"Codex name: {b.session_name}")
            if b.thread_title and b.thread_title != b.session_name:
                lines.append(
                    "thread title: " + truncate(
                        b.thread_title, max(30, detail_width - display_width("thread title: "))
                    )
                )
            if b.cwd:
                lines.append(f"cwd: {b.cwd}")
''',
    "detail label metadata",
)

s = replace_once(
    s,
    '''            "session_id": b.session_id,
            "title": b.title,
            "cwd": b.cwd,
''',
    '''            "session_id": b.session_id,
            "title": b.title,
            "session_name": b.session_name or None,
            "thread_title": b.thread_title or None,
            "project_id": b.project_id or None,
            "project_name": b.project_name or None,
            "cwd": b.cwd,
''',
    "JSON session metadata",
)

s = replace_once(
    s,
    '''        "session_id", "title", "cwd", "models", "service_tiers", "credit_mode",
''',
    '''        "session_id", "title", "session_name", "thread_title", "project_id",
        "project_name", "cwd", "models", "service_tiers", "credit_mode",
''',
    "CSV metadata headers",
)

s = replace_once(
    s,
    '''            b.session_id,
            b.title,
            b.cwd,
            ",".join(model_names(b.usage_by_model.keys())),
''',
    '''            b.session_id,
            b.title,
            b.session_name,
            b.thread_title,
            b.project_id,
            b.project_name,
            b.cwd,
            ",".join(model_names(b.usage_by_model.keys())),
''',
    "CSV metadata values",
)

script_path.write_text(s, encoding="utf-8")


test_path = Path("tests/test_codex_usage.py")
t = test_path.read_text(encoding="utf-8")
t = replace_once(t, 'self.assertIn("1.6.0", proc.stdout)', 'self.assertIn("1.6.1", proc.stdout)', "version test")

new_tests = r'''
    def test_v161_prefers_codex_name_and_project_over_template_prompt(self):
        sid_named = "019ffabc-1234-7000-8000-123456789101"
        sid_template = "019ffabc-1234-7000-8000-123456789102"
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            db = sqlite3.connect(home / "state_5.sqlite")
            db.executescript(
                """
                CREATE TABLE threads (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    title TEXT,
                    preview TEXT,
                    first_user_message TEXT,
                    project_id TEXT,
                    cwd TEXT,
                    source TEXT,
                    thread_source TEXT,
                    agent_nickname TEXT,
                    agent_role TEXT,
                    model_provider TEXT,
                    created_at INTEGER,
                    updated_at INTEGER,
                    rollout_path TEXT,
                    git_origin_url TEXT,
                    git_branch TEXT
                );
                CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE project_roots (
                    project_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    PRIMARY KEY(project_id, position)
                );
                """
            )
            db.execute("INSERT INTO projects(id,name) VALUES(?,?)", ("p1", "steerRL"))
            db.execute("INSERT INTO projects(id,name) VALUES(?,?)", ("p2", "knowing-to-see"))
            template = "读取 AGENTS.md、docs/PROJECT_STATUS.md，并继续推进当前任务"
            db.execute(
                "INSERT INTO threads(id,name,title,preview,project_id,cwd) VALUES(?,?,?,?,?,?)",
                (sid_named, "Sparse-1 S3 对比实验", template, template, "p1", "/tmp/steerRL"),
            )
            db.execute(
                "INSERT INTO threads(id,name,title,preview,project_id,cwd) VALUES(?,?,?,?,?,?)",
                (sid_template, None, template, template, "p2", "/tmp/knowing-to-see"),
            )
            db.commit()
            db.close()

            index = self.mod.load_thread_index(home)
            named = self.mod.RawSession(sid_named, Path("named.jsonl"), cwd="/tmp/steerRL")
            templated = self.mod.RawSession(sid_template, Path("template.jsonl"), cwd="/tmp/knowing-to-see")
            self.assertEqual(index[sid_named]["project_name"], "steerRL")
            self.assertEqual(
                self.mod.session_title(named, index),
                "[steerRL] Sparse-1 S3 对比实验",
            )
            self.assertEqual(
                self.mod.session_title(templated, index),
                f"[knowing-to-see] {template}",
            )

    def test_v161_old_state_schema_uses_cwd_project_context(self):
        sid = "019ffabc-1234-7000-8000-123456789103"
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            db = sqlite3.connect(home / "state_5.sqlite")
            db.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, cwd TEXT)")
            db.execute(
                "INSERT INTO threads(id,title,cwd) VALUES(?,?,?)",
                (sid, "读取 AGENTS.md、docs/PROJECT_STATUS.md", "/tmp/project-alpha"),
            )
            db.commit()
            db.close()
            index = self.mod.load_thread_index(home)
            session = self.mod.RawSession(sid, Path("old.jsonl"), cwd="/tmp/project-alpha")
            self.assertEqual(
                self.mod.session_title(session, index),
                "[project-alpha] 读取 AGENTS.md、docs/PROJECT_STATUS.md",
            )

    def test_v161_duplicate_labels_receive_stable_session_suffixes(self):
        first = self.mod.Bucket(
            session_id="019ffabc-1234-7000-8000-123456789111",
            title="[project] Template task",
        )
        second = self.mod.Bucket(
            session_id="019ffabc-5678-7000-8000-123456789222",
            title="[project] Template task",
        )
        buckets = {first.session_id: first, second.session_id: second}
        self.mod._disambiguate_bucket_titles(buckets)
        self.assertNotEqual(first.title, second.title)
        self.assertTrue(first.title.endswith(first.session_id[:12]))
        self.assertTrue(second.title.endswith(second.session_id[:12]))

'''

anchor = '\n\nif __name__ == "__main__":\n'
if "test_v161_prefers_codex_name_and_project_over_template_prompt" not in t:
    t = replace_once(t, anchor, '\n' + new_tests + anchor, "v1.6.1 tests")
test_path.write_text(t, encoding="utf-8")


readme_path = Path("README.md")
r = readme_path.read_text(encoding="utf-8")
section = '''## v1.6.1: project-aware session labels

The `SESSION` column now prefers the explicit name shown by Codex (`threads.name`) and prefixes it with the assigned Codex project when available. If no explicit name exists, the project is combined with Codex's preview/title; older state databases fall back to the repository/cwd name. This keeps templated prompts distinguishable across projects:

```text
[steerRL] Sparse-1 S3 comparison
[knowing-to-see] Read AGENTS.md and continue the current stage
```

If two visible sessions still resolve to the exact same label, a stable short session ID is appended. DETAILS, JSON, and CSV expose the underlying session name, thread title, project ID, and project name. This update reads only `state_5.sqlite` metadata and does not require a token-cache rebuild.

'''
if "## v1.6.1: project-aware session labels" not in r:
    r = replace_once(r, "# codex-usage\n\n", "# codex-usage\n\n" + section, "README v1.6.1 section")
readme_path.write_text(r, encoding="utf-8")


zh_path = Path("README.zh-CN.md")
z = zh_path.read_text(encoding="utf-8")
zh_section = '''## v1.6.1：项目感知的 session 名称

`SESSION` 列现在优先使用 Codex 界面中显式设置的 session 名称（`threads.name`），并在可用时把 Codex project 名称放在最前面。若没有显式名称，则组合 project 与 Codex 的 preview/title；旧版状态数据库会退回到仓库名或 cwd 目录名。这样，即使多个项目都使用同一套模板化首条指令，也能直接区分：

```text
[steerRL] Sparse-1 S3 对比实验
[knowing-to-see] 读取 AGENTS.md 并继续当前阶段
```

若多个可见 session 最终仍得到完全相同的标签，工具会追加稳定的短 session ID。DETAILS、JSON、CSV 也会提供 session name、thread title、project ID 和 project name。本次更新只读取 `state_5.sqlite` 元数据，不需要重建 token cache。

'''
if "## v1.6.1：项目感知的 session 名称" not in z:
    z = replace_once(z, "# codex-usage\n\n", "# codex-usage\n\n" + zh_section, "Chinese README v1.6.1 section")
zh_path.write_text(z, encoding="utf-8")


changelog_path = Path("CHANGELOG.md")
c = changelog_path.read_text(encoding="utf-8")
change = '''## 1.6.1 — 2026-08-30

- Preferred Codex's explicit user-facing thread `name` over the generated first-prompt title.
- Added project-aware session labels using `threads.project_id` and `projects.name`, with repository/cwd fallback for older state databases.
- Prefixed project context before templated titles so identical startup instructions remain distinguishable across projects.
- Added stable short-session suffixes when multiple visible rows still resolve to the same label.
- Exposed session name, underlying thread title, project ID, and project name in DETAILS, JSON, and CSV.
- Kept backward compatibility with older `state_5.sqlite` schemas; no token-cache rebuild is required.

'''
if "## 1.6.1 — 2026-08-30" not in c:
    c = replace_once(c, "# Changelog\n\n", "# Changelog\n\n" + change, "changelog v1.6.1")
changelog_path.write_text(c, encoding="utf-8")
