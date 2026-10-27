from __future__ import annotations

import argparse
from pathlib import Path
import re


def command_argument(text: str, start: int) -> tuple[str, int]:
    if text[start] != "{":
        raise ValueError("Expected a braced LaTeX argument")
    depth = 1
    position = start + 1
    while position < len(text) and depth:
        if text[position] == "{" and text[position - 1] != "\\":
            depth += 1
        elif text[position] == "}" and text[position - 1] != "\\":
            depth -= 1
        position += 1
    if depth:
        raise ValueError("Unbalanced LaTeX argument")
    return text[start + 1:position - 1], position


def simplify_bibinfo(text: str) -> str:
    while r"\bibinfo{" in text:
        start = text.index(r"\bibinfo{")
        _, position = command_argument(text, start + len(r"\bibinfo"))
        content, end = command_argument(text, position)
        text = text[:start] + content + text[end:]
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--aux", type=Path, required=True)
    parser.add_argument("--bbl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    text = args.input.read_text(encoding="utf-8-sig")
    while r"\shortstack{" in text:
        start = text.index(r"\shortstack{")
        content, end = command_argument(text, start + len(r"\shortstack"))
        content = re.sub(r"\\\\(?:\[[^]]*\])?", " ", content)
        text = text[:start] + content + text[end:]
    aux = args.aux.read_text(encoding="utf-8")
    bibliography = args.bbl.read_text(encoding="utf-8")
    numbers = dict(re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]+)\}", aux))
    citation_labels = {}
    for label, key in re.findall(r"\\bibitem\[\{(.*?)\}\]\{([^}]+)\}", bibliography, re.S):
        match = re.match(r"(.*?)\((\d{4}[a-z]?)\)", label, re.S)
        if not match:
            raise ValueError("Unresolved bibliography label: " + key)
        citation_labels[key] = (re.sub(r"\s+", " ", match[1]).replace("~", " "), match[2])
    def citation(match):
        labels = [citation_labels[key.strip()] for key in match[2].split(",")]
        if match[1] == "citet":
            return "; ".join(author + " (" + year + ")" for author, year in labels)
        return "(" + "; ".join(author + ", " + year for author, year in labels) + ")"
    text = re.sub(r"\\(citet|citep|citealp|cite)\{([^}]+)\}", citation, text)
    def reference(match):
        if match[2] not in numbers:
            raise ValueError("Unresolved manuscript reference: " + match[2])
        value = numbers[match[2]]
        return "(" + value + ")" if match[1] == "eqref" else value
    text = re.sub(r"\\(eqref|ref)\{([^}]+)\}", reference, text)
    def equation(match):
        body = match[1]
        label = re.search(r"\\label\{([^}]+)\}", body)
        body = re.sub(r"\\label\{[^}]+\}", "", body).strip()
        number = r"\qquad (" + numbers[label[1]] + ")" if label else ""
        return "\\[\n" + body + number + "\n\\]"
    text = re.sub(r"\\begin\{equation\}(.*?)\\end\{equation\}", equation, text, flags=re.S)
    for environment, prefix in (("table", "Table"), ("figure", "Figure")):
        pattern = r"\\begin\{" + environment + r"\}(?:\[[^]]*\])?(.*?)\\end\{" + environment + r"\}"
        def caption(match):
            content = match[1]
            label = re.search(r"\\label\{([^}]+)\}", content)
            if label:
                content = content.replace(r"\caption{", r"\caption{" + prefix + " " + numbers[label[1]] + ". ", 1)
            return r"\begin{" + environment + "}" + content + r"\end{" + environment + "}"
        text = re.sub(pattern, caption, text, flags=re.S)
    text = re.sub(r"\\label\{[^}]+\}", "", text)
    text = text.replace(r"\begin{tabular}{lp{0.66\linewidth}}", r"\begin{tabular}{p{0.27\linewidth}p{0.66\linewidth}}")
    text = text.replace(r"\begin{tabular}{lp{0.59\linewidth}}", r"\begin{tabular}{p{0.24\linewidth}p{0.70\linewidth}}")
    text = text.replace(r"\begin{tabular}{p{0.24\linewidth}p{0.28\linewidth}cr}",
                        r"\begin{tabular}{p{0.24\linewidth}p{0.28\linewidth}p{0.16\linewidth}p{0.26\linewidth}}")
    text = text.replace(r"\begin{tabular}{p{0.16\linewidth}p{0.25\linewidth}p{0.23\linewidth}p{0.20\linewidth}}",
                        r"\begin{tabular}{p{0.20\linewidth}p{0.26\linewidth}p{0.28\linewidth}p{0.24\linewidth}}")
    title = re.search(r"\\title\s*\[[^]]*\]\{([^}]+)\}", text)[1]
    abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text, re.S)[1]
    keywords = re.search(r"\\begin\{keywords\}(.*?)\\end\{keywords\}", text, re.S)[1].replace(r"\sep", ";")
    body = text.split(r"\maketitle", 1)[1].split(r"\bibliographystyle", 1)[0]
    body = body.replace(r"\linenumbers", "").replace(r"\FloatBarrier", "")
    entries = bibliography[bibliography.index(r"\bibitem"):bibliography.rindex(r"\end{thebibliography}")]
    entries = simplify_bibinfo(entries)
    entries = re.sub(r"\\bibitem\[\{.*?\}\]\{[^}]+\}", r"\\par\\noindent ", entries, flags=re.S)
    entries = re.sub(r"(?m)^%.*$", "", entries).replace(r"\newblock", " ")
    entries = entries.replace(r"\URLprefix", "URL: ").replace(r"\DOIprefix", "DOI: ")
    entries = re.sub(r"\\doi\{([^}]+)\}", r"\\url{https://doi.org/\1}", entries)
    entries = re.sub(r"\\natexlab\{([^}]+)\}", r"\1", entries)
    front = r"""\documentclass[11pt]{article}
\usepackage{amsmath,amssymb,graphicx,booktabs,hyperref}
\title{""" + title + r"""}
\author{Yidan Zheng \and Yanhong Liu \and Haiwang Zhong}
\date{}
\begin{document}
\maketitle
\noindent Sichuan Energy Internet Research Institute, Tsinghua University, Chengdu, China.\\
Department of Electrical Engineering, Tsinghua University, Beijing, China.\\
State Key Laboratory of Power System Operation and Control, Tsinghua University, Beijing, China.\\
Corresponding author: Haiwang Zhong, \texttt{zhonghw@tsinghua.edu.cn}.
\begin{abstract}
""" + abstract + "\n\\end{abstract}\n\\noindent\\textbf{Keywords:} " + keywords + "\n\n"
    args.output.write_text(front + body + "\n\\section*{References}\n" + entries + "\n\\end{document}\n", encoding="utf-8")
    print("Word source resolves all citations, references, and numbered equations.")


if __name__ == "__main__":
    main()
