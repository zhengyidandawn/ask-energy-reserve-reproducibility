from __future__ import annotations

import argparse
import re
from pathlib import Path
import zipfile

from lxml import etree


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
WORD = "{" + NS["w"] + "}"


def property_element(parent, name: str):
    element = parent.find("w:" + name, NS)
    if element is None:
        element = etree.Element(WORD + name)
        parent.insert(0, element)
    return element


def normalize(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        members = [(member, archive.read(member.filename)) for member in archive.infolist()]
    root = etree.fromstring(dict((member.filename, data) for member, data in members)["word/document.xml"])
    for paragraph in root.findall("w:body/w:p", NS):
        text = "".join(paragraph.xpath(".//w:t/text()", namespaces=NS))
        if re.match(r"^Figure\s+\d+[.:]", text):
            properties = property_element(paragraph, "pPr")
            property_element(properties, "keepLines").set(WORD + "val", "1")
            property_element(properties, "keepNext").set(WORD + "val", "0")
            preceding = paragraph.getprevious()
            if preceding is not None and preceding.tag == WORD + "p" and preceding.find(".//w:drawing", NS) is not None:
                image_properties = property_element(preceding, "pPr")
                property_element(image_properties, "keepNext").set(WORD + "val", "1")
                property_element(image_properties, "keepLines").set(WORD + "val", "1")
    tables = root.findall("w:body/w:tbl", NS)
    for table in tables:
        caption = table.getprevious()
        if caption is not None and caption.tag == WORD + "p":
            property_element(property_element(caption, "pPr"), "keepNext")
        table_rows = table.findall("w:tr", NS)
        for row_index, row in enumerate(table_rows):
            properties = property_element(row, "trPr")
            property_element(properties, "cantSplit")
            if row_index == 0:
                property_element(properties, "tblHeader")
            for paragraph in row.findall(".//w:p", NS):
                properties = property_element(paragraph, "pPr")
                property_element(properties, "keepLines")
                keep = property_element(properties, "keepNext")
                keep.set(WORD + "val", "1" if row_index < len(table_rows) - 1 else "0")
    payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    styles_payload = None
    style_data = next((data for member, data in members if member.filename == "word/styles.xml"), None)
    if style_data is not None:
        styles = etree.fromstring(style_data)
        for style in styles.findall("w:style", NS):
            identifier = style.get(WORD + "styleId", "")
            if identifier in ("Title", "Subtitle") or identifier.startswith("Heading"):
                color = property_element(property_element(style, "rPr"), "color")
                color.attrib.clear()
                color.set(WORD + "val", "000000")
        styles_payload = etree.tostring(styles, xml_declaration=True, encoding="UTF-8", standalone=True)
    temporary = path.with_suffix(".pagination.docx")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member, data in members:
            if member.filename == "word/document.xml":
                data = payload
            elif member.filename == "word/styles.xml" and styles_payload is not None:
                data = styles_payload
            archive.writestr(member, data)
    temporary.replace(path)
    return len(tables)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print("Kept table captions and rows together:", normalize(args.path))


if __name__ == "__main__":
    main()
