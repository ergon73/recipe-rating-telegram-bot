"""Fail closed on common private artifacts in the Git index; never print their content."""

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(rb"\b[0-9]{6,}:[A-Za-z0-9_-]{20,}")


def forbidden(path: str) -> bool:
    parts = Path(path).parts
    name = parts[-1]
    return (
        (name.startswith(".env") and name != ".env.example")
        or name == "favorites.json"
        or name.endswith((".db", ".sqlite", ".sqlite3", ".log", ".pyc"))
        or any(p in {".venv", "data", "__pycache__", ".pytest_cache"} for p in parts)
    )


def main():
    git = shutil.which("git")
    if not git:
        raise SystemExit("Git is required.")
    # Git path resolved from PATH; no shell, no user-supplied command.
    result = subprocess.run(  # noqa: S603
        [git, "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    )
    paths = [p for p in result.stdout.decode("utf-8").split("\0") if p]
    failures = []
    for path in paths:
        if forbidden(path):
            failures.append((path, "private artifact"))
            continue
        # Scan what will actually be committed, not an unstaged working-tree replacement.
        content = subprocess.run(  # noqa: S603
            [git, "show", f":{path}"], cwd=ROOT, capture_output=True, check=True
        ).stdout
        if SECRET.search(content):
            failures.append((path, "credential-like value"))
    for path, reason in failures:
        print(f"FAIL: {path}: {reason}")
    if not paths:
        raise SystemExit("No tracked files; stage the reviewed public files first.")
    if failures:
        raise SystemExit(1)
    print(f"Public tree guard: {len(paths)} files checked, no findings.")


if __name__ == "__main__":
    main()
