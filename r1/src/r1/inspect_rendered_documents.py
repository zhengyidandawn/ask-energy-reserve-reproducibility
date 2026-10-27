from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sys

import pymupdf
from PIL import Image, ImageDraw

from run_paired_services import PROJECT


def contact_sheets(paths: list[Path], output: Path, prefix: str) -> None:
    for start in range(0, len(paths), 12):
        page_paths = paths[start:start + 12]
        sheet = Image.new("RGB", (1360, 1470), "#dddddd")
        drawing = ImageDraw.Draw(sheet)
        for index, path in enumerate(page_paths):
            picture = Image.open(path).convert("RGB")
            picture.thumbnail((330, 450))
            left = index % 4 * 340 + (340 - picture.width) // 2
            top = index // 4 * 490 + 28
            sheet.paste(picture, (left, top))
            drawing.text((index % 4 * 340 + 8, index // 4 * 490 + 7), path.stem, fill="black")
        sheet.save(output / f"{prefix}_contact_{start // 12 + 1:02d}.png")


def main() -> None:
    results = PROJECT / "results"
    output = results / "final_visual_review"
    output.mkdir(parents=True, exist_ok=True)
    for path in output.glob("*_contact_*.png"):
        path.unlink()
    audit = {}
    for name in ("Manuscript_unmark", "Manuscript_mark", "Supplementary_Material"):
        document = pymupdf.open(results / (name + ".pdf"))
        paths = []
        text = "\n".join(page.get_text() for page in document)
        for index, page in enumerate(document):
            path = output / f"{name}_{index + 1:02d}.png"
            page.get_pixmap(dpi=105).save(path)
            paths.append(path)
        audit[name] = {"pages": len(document), "characters": len(text), "undefined_reference_tokens": text.count("??"),
            "overdue_pending_statements": bool(re.search(r"remain(?:s)? pending|pending validation|remain to be conducted|not included in the current results", text, re.I)),
            "local_drive_paths": bool(re.search(r"[A-Z]:[\\/]", text))}
        (output / (name + ".txt")).write_text(text, encoding="utf-8")
        contact_sheets(paths, output, name)
    for directory in (results / "word_render_r1").iterdir():
        if not directory.is_dir():
            continue
        paths = sorted(directory.glob("page-*.png"), key=lambda path: int(path.stem.split("-")[-1]))
        contact_sheets(paths, output, directory.name + "_word")
        pdf = directory / (directory.name + ".pdf")
        if pdf.exists():
            document = pymupdf.open(pdf)
            text = "\n".join(page.get_text() for page in document)
            (output / (directory.name + "_word.txt")).write_text(text, encoding="utf-8")
            audit[directory.name + "_word"] = {"pages": len(document), "characters": len(text), "undefined_reference_tokens": text.count("??"),
                "local_drive_paths": bool(re.search(r"[A-Z]:[\\/]", text))}
    audit["figure_selectable_text"] = {}
    for name in ("F1_ASK_boundary_workflow.pdf", "F3_rolling_scheme.pdf", "P3_state_density_risk.pdf"):
        document = pymupdf.open(PROJECT / "elsarticle_unmark" / "figures" / name)
        audit["figure_selectable_text"][name] = sum(len(page.get_text()) for page in document)
    (output / "render_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
