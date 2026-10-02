"""Fail if PNEUMORA references unrelated SnowCore products or secrets."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (r"SNOWCORE_REAL", r"SNOWCORE_INDUSTRIES", r"\bPIADE\b", r"password\s*=", r"private[_-]?key")
SKIP = {".venv", "__pycache__", ".pytest_cache", "data"}


def main() -> int:
    findings = []
    for path in ROOT.rglob("*"):
        if path.resolve() == Path(__file__).resolve():
            continue
        if not path.is_file() or any(part in SKIP for part in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".md", ".json", ".sql", ".toml", ".yml", ".yaml"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN:
            if re.search(pattern, text, flags=re.IGNORECASE):
                findings.append(f"{path.relative_to(ROOT)}: {pattern}")
    if findings:
        raise SystemExit("Isolation check failed:\n" + "\n".join(findings))
    print("PNEUMORA isolation check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
