from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [ROOT / "data", ROOT / "results"]
FORBIDDEN = ("GD", "China province", "Guangdong", "中国", "省份")


def main() -> int:
    violations: list[str] = []
    for directory in SCAN_DIRS:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".csv", ".json", ".jsonl", ".txt"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for term in FORBIDDEN:
                if term.lower() in text.lower():
                    violations.append(f"{path.relative_to(ROOT)} contains {term!r}")
    if violations:
        raise SystemExit("Public-scope check failed:\n" + "\n".join(violations))
    print("Public-scope check passed: no private-region material in distributed data/results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
