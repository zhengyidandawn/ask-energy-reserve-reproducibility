from __future__ import annotations

import argparse
from pathlib import Path
import re


def reachable_labels(root: Path) -> set[str]:
    pending = [root / "main.tex", root / "Supplementary_Material.tex"]
    visited = set()
    labels = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        source = re.sub(r"(?<!\\)%[^\n]*", "", path.read_text(encoding="utf-8-sig"))
        labels.update(re.findall(r"\\label\{([^}]+)\}", source))
        for relative in re.findall(r"\\input\{([^}]+)\}", source):
            target = root / relative
            pending.append(target if target.suffix else target.with_suffix(".tex"))
    return labels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revised", type=Path, required=True)
    parser.add_argument("--marked", type=Path, required=True)
    parser.add_argument("--baseline-aux", type=Path, required=True)
    args = parser.parse_args()
    current = reachable_labels(args.revised)
    baseline = dict(re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]+)\}", args.baseline_aux.read_text(encoding="utf-8")))
    count = 0
    for path in args.marked.rglob("*.tex"):
        source = path.read_text(encoding="utf-8-sig")
        def reference(match):
            nonlocal count
            key = match[2]
            if key in current:
                return match[0]
            if key not in baseline:
                raise ValueError("Unresolved historical reference: " + key)
            count += 1
            value = baseline[key]
            return "(" + value + ")" if match[1] == "eqref" else value
        revised = re.sub(r"\\(eqref|ref)\{([^}]+)\}", reference, source)
        if revised != source:
            path.write_text(revised, encoding="utf-8")
    print(f"Resolved {count} references to deleted objects using original AEI numbering.")


if __name__ == "__main__":
    main()
