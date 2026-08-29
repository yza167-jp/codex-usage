from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing anchor: {label}")
    return text.replace(old, new, 1)


script = Path("codex-usage")
s = script.read_text(encoding="utf-8")
s = replace_once(
    s,
    '''    repo_name = _git_origin_project_label(dbrow.get("git_origin_url"))
    context = project_name or repo_name or _cwd_project_label(cwd)
''',
    '''    repo_name = _git_origin_project_label(dbrow.get("git_origin_url"))
    # The concrete cwd is usually more discriminative than the shared remote
    # repository name (for example across worktrees). A canonical Codex project
    # still takes precedence when one is assigned.
    context = project_name or _cwd_project_label(cwd) or repo_name
''',
    "context priority",
)
script.write_text(s, encoding="utf-8")


readme = Path("README.md")
r = readme.read_text(encoding="utf-8")
r = r.replace(
    "Fall back to project roots, git repository name, or cwd basename",
    "Fall back to project roots, cwd basename, or git repository name",
)
readme.write_text(r, encoding="utf-8")


changelog = Path("CHANGELOG.md")
c = changelog.read_text(encoding="utf-8")
c = c.replace(
    "with repository/cwd fallback for older state databases",
    "with cwd/repository fallback for older state databases",
)
changelog.write_text(c, encoding="utf-8")
