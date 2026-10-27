from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import sys
import zipfile

from lxml import etree

from run_paired_services import PROJECT

NS={"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def patch_document(path: Path, replacements: dict[int,str]) -> None:
    with zipfile.ZipFile(path) as package:
        parts={entry.filename:package.read(entry.filename) for entry in package.infolist()}
    document=etree.fromstring(parts["word/document.xml"])
    paragraphs=document.findall("w:body/w:p",NS)
    for index,value in replacements.items():
        paragraph=paragraphs[index]
        runs=paragraph.findall("w:r",NS)
        pattern=deepcopy(runs[0])
        for child in list(paragraph):
            if child.tag!="{"+NS["w"]+"}pPr":
                paragraph.remove(child)
        for child in list(pattern):
            if child.tag!="{"+NS["w"]+"}rPr":
                pattern.remove(child)
        text=etree.SubElement(pattern,"{"+NS["w"]+"}t")
        text.text=value
        paragraph.append(pattern)
    parts["word/document.xml"]=etree.tostring(document,encoding="UTF-8",xml_declaration=True,standalone=True)
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as package:
        for name,data in parts.items():
            package.writestr(name,data)


def main() -> None:
    submit=PROJECT.parent/"提交_AEI_R1"
    source=(PROJECT/"elsarticle_unmark"/"main.tex").read_text(encoding="utf-8")
    title=re.search(r"\\title\s*\[.*?\]\{(.*?)\}",source).group(1)
    patch_document(submit/"CoverLetter.docx",{
        1:f"Please consider the revised manuscript ADVEI-D-26-08441, ‘{title},’ for the Energy Virtual Special Issue of Advanced Engineering Informatics. We thank the editor and three reviewers for the major-revision opportunity.",
        2:"The revision connects a language-based study request to checked decision-time information, a structured plan, recorded authorization, and deterministic reserve evidence. It adds independent annotation, repeated hosted-service evaluation, matched interfaces, expert plans, clarification dialogues, and public high-resolution load validation.",
        3:"Three annotators assessed 168 requests, including 48 independently authored requests with Fleiss’ kappa of 0.932. Three experts prepared 72 plans for 24 matched requests, and a separate written review recorded authorization and clarification decisions. A separate protocol for complete drafts provides 480 initial responses and 54 automatic feedback responses on these requests, with 75.1–98.1% of variable inputs available for verification. Repeated service evaluation archives versions, prompts, decoding settings, usage, and timing. Matched form, deterministic-parser, JSON-schema, and function-calling comparisons separate interpretation from validation.",
        4:"Public quarter-hourly load from Germany, Austria, Belgium, and the Netherlands provides 48 rolling windows and 138,240 held-out decisions. A frozen-margin comparison places all 256 later policy-window combinations above 0.95 empirical coverage. All eight policies are compared through cost, coverage, reserve, and tail shortfall under this protocol, with paired family-adjusted cost intervals. Nine study-plan traces connect field changes to the executed calculation.",
        5:"The Discussion explains the contribution of request interpretation, deterministic checking, clarification, and numerical calibration. The evidence supports the evaluated offline study workflow. Clean and marked manuscripts, the Supplementary Material, detailed reviewer responses, and source packages accompany the revision.",
        6:"We believe that the revised manuscript remains aligned with the Energy Virtual Special Issue of Advanced Engineering Informatics because it connects energy decisions, available information, reliability, and computational evidence. Our study addresses engineering informatics through the trace from a human request to structured information and numerical execution. We submit the revised manuscript exclusively to Advanced Engineering Informatics. We have reviewed it and take responsibility for its content.",
        7:"Thank you again for considering the revised manuscript for the Energy Virtual Special Issue of Advanced Engineering Informatics."
    })
    highlights=["Checked study plans connect language requests with reserve calculations.",
        "Independent annotation and repeated calls evaluate request-level reliability.",
        "Matched interfaces separate interpretation from deterministic validation.",
        "Public quarter-hourly load supports 138,240 held-out reserve decisions.",
        "Common reliability constraints connect reserve cost with physical shortfall."]
    assert all(len(line)<=85 for line in highlights)
    patch_document(submit/"Highlights.docx",{index+1:line for index,line in enumerate(highlights)})
    abstract=re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}",source,re.S).group(1).strip()
    abstract=re.sub(r"\\%","%",abstract)
    abstract=re.sub(r"\\(?:textbf|emph)\{([^{}]*)\}",r"\1",abstract)
    keywords=re.search(r"\\begin\{keywords\}(.*?)\\end\{keywords\}",source,re.S).group(1).strip().replace(r"\sep",";")
    (submit/"题目摘要关键词.txt").write_text("Title\n"+title+"\n\nAbstract\n"+abstract+"\n\nKeywords\n"+keywords+"\n",encoding="utf-8")
    print("Submission text and retained Word templates updated.")


if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
