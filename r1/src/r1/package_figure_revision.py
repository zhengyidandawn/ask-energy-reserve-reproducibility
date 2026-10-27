"""Synchronize completed publication artifacts without running experiments."""
from pathlib import Path
import csv
import hashlib
import json
import os
import shutil
import zipfile

PROJECT=Path(__file__).resolve().parents[2]
SUBMISSION=PROJECT.parent/'提交_AEI_R1'
ROUND=PROJECT/'results'/'figure_revision_20261026'


def native(path):
    value=str(path.absolute())
    return Path('\\\\?\\'+value) if os.name=='nt' and not value.startswith('\\\\?\\') else path


def sha(path):
    with native(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def copy_file(source,target):
    native(target.parent).mkdir(parents=True,exist_ok=True)
    shutil.copy2(native(source),native(target))


def copy_tree(source,target):
    base=native(source)
    for path in base.rglob('*'):
        if not path.is_file():continue
        relative=path.relative_to(base)
        if any(part in {'output','__pycache__','.git'} for part in relative.parts):continue
        if path.suffix in {'.pyc','.aux','.log','.fls','.fdb_latexmk','.out','.toc','.blg','.bbl','.abs'}:continue
        copy_file(path,target/relative)


def archive_tree(source,target):
    base=native(source)
    with zipfile.ZipFile(native(target),'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,
                         allowZip64=True,strict_timestamps=False) as archive:
        for path in sorted(base.rglob('*')):
            if path.is_file():
                relative=path.relative_to(base)
                archive.write(path,source.name+'/'+relative.as_posix())


def main():
    assert SUBMISSION.parent.resolve()==PROJECT.parent.resolve()
    files={
        'results/Manuscript_unmark.pdf':'Manuscript_unmark.pdf',
        'results/Manuscript_mark.pdf':'Manuscript_mark.pdf',
        'results/Manuscript_unmark.docx':'Manuscript_unmark.docx',
        'results/Supplementary_Material.pdf':'补充材料.pdf',
        'article/Response_to_Reviewers_AEI_R1_EN.docx':'Response_to_Reviewers_AEI_R1_EN.docx',
        'article/Response_to_Reviewers_AEI_R1_CN.docx':'Response_to_Reviewers_AEI_R1_CN.docx',
        'article/CoverLetter.docx':'CoverLetter.docx',
        'article/Highlights.docx':'Highlights.docx',
        'article/题目摘要关键词.txt':'题目摘要关键词.txt'}
    for source,target in files.items():copy_file(PROJECT/source,SUBMISSION/target)
    for source,target in [('elsarticle_unmark','Source_unmark'),('elsarticle_mark','Source_mark'),('src','Compilation_scripts')]:
        copy_tree(PROJECT/source,SUBMISSION/target)
    package=SUBMISSION/'Reproducibility_package_AEI_R1'
    for source in files:copy_file(PROJECT/source,package/source)
    for source in ['elsarticle_unmark','elsarticle_mark']:
        copy_tree(PROJECT/source,package/source)
    copy_tree(PROJECT/'src',package/'src')
    copy_tree(PROJECT/'article/templates',package/'article/templates')
    for source in ['results/integrated_r1/response_template_fidelity.json',
                   'results/selective_marking/marking_manifest.json']:
        copy_file(PROJECT/source,package/source)
    output=package/'results/figure_revision_20261026'
    for path in ROUND.iterdir():
        if path.suffix=='.json' and not (path.name.endswith('_provenance.json') or path.name in {'public_figure_manifest.json','study_design_figure_sources.json'}):
            continue
        if path.is_file() and path.suffix in {'.csv','.json','.pdf','.svg','.png'}:
            copy_file(path,output/path.name)
    copy_tree(ROUND/'source_csv',output/'source_csv')
    for path in ROUND.glob('R1_F*_provenance.json'):
        manifest=json.loads(path.read_text(encoding='utf-8'))
        for record in manifest['source_files'].values():
            snapshot=ROUND/record['archived_csv']
            assert sha(snapshot)==record['sha256']
            copy_file(snapshot,package/record['package_source_path'])
    requirements=package/'requirements.txt'
    text=requirements.read_text(encoding='utf-8-sig')
    if not any(line.lower().startswith('matplotlib==') for line in text.splitlines()):
        requirements.write_text(text.rstrip()+'\nmatplotlib==3.10.7\n',encoding='utf-8')
    readme=package/'README.txt'
    text=readme.read_text(encoding='utf-8-sig')
    note=('\nPublication graphics\n'
          'The scripts src/r1/plot_study_design.py, plot_request_evidence.py, and\n'
          'plot_public_evidence.py read completed CSV records and prediction caches.\n'
          'They write PDF, SVG, and PNG assets without fitting models, making service\n'
          'calls, or resampling intervals. Figure data and source hashes are retained\n'
          'in results/figure_revision_20261026. Matplotlib 3.10.7 renders the graphics.\n')
    if '\nPublication graphics\n' not in text:readme.write_text(text.rstrip()+'\n'+note,encoding='utf-8')
    rows=[]
    base=native(package)
    for path in sorted(base.rglob('*')):
        if not path.is_file() or path.name=='package_manifest.csv':continue
        rows.append({'path':str(path.relative_to(base)),'bytes':path.stat().st_size,'sha256':sha(path)})
    with (package/'package_manifest.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['path','bytes','sha256'])
        writer.writeheader();writer.writerows(rows)
    print(f'Inventoried {len(rows)} reproducibility files.',flush=True)
    for source,target in [('Source_unmark','LaTeX_Source_unmark_AEI_R1.zip'),
                          ('Source_mark','LaTeX_Source_mark_AEI_R1.zip'),
                          ('Reproducibility_package_AEI_R1','Reproducibility_package_AEI_R1.zip')]:
        archive_tree(SUBMISSION/source,SUBMISSION/target)
        print(f'Created {target}',flush=True)


if __name__=='__main__':main()
