#!/usr/bin/python3 -I
# Build the book (or any Pandoc Markdown file) into PDF, HTML and plain text.
#
# Usage: build.py [--formats pdf,html,txt] [--paper b5|a4|letter] [--gray]
#                 OUTDIR [INPUT.md...]
#
# Without INPUT files, builds the book itself, into OUTDIR/book.*: the chapters
# listed in metadata.yaml, in that order, with the parts and the switches
# between front matter, main matter, appendices and back matter between them,
# run through tools/bookfilter.py (which numbers references by label).
#
# The PDF uses LuaLaTeX with KOMA-Script's scrbook class and style/book.tex.
# Fonts are Libertinus Serif and Source Code Pro when installed (Fedora:
# texlive-libertinus-fonts, texlive-sourcecodepro); otherwise LaTeX's default
# Latin Modern is used.

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

book = Path(__file__).resolve().parent.parent
style = book / 'style'

def have_tex_file(filename):
    return subprocess.run(['kpsewhich', filename], capture_output=True).returncode == 0

def pandoc(inputs, *args):
    cmd = ['pandoc', '-f', 'markdown+pandoc_title_block', *map(str, inputs), *args, *book_args]
    subprocess.run(cmd, check=True)

def roman(n):
    return ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'][n - 1]

def book_inputs(gen):
    """Lay out the book from metadata.yaml: returns the input files, in order,
    and writes the part and marker files and the labels file into gen."""
    structure = yaml.safe_load((book / 'metadata.yaml').read_text().split('---')[1])['book']
    gen.mkdir(parents=True, exist_ok=True)
    labels, inputs = {}, [book / 'metadata.yaml']

    def chapter(name, label=None):
        path = book / 'chapters' / f'{name}.md'
        if not path.exists():
            sys.exit(f'build.py: {path} is listed in metadata.yaml but does not exist')
        first = path.read_text().split('\n', 1)[0]
        if label and not re.match(r'^# .*\{#' + re.escape(label) + r'[ }]', first):
            sys.exit(f'build.py: {path} must start with a heading labeled {{#{label}}}')
        inputs.append(path)

    def marker(name):
        path = gen / f'{name}.md'
        path.write_text(f'::: {{.{name}}}\n:::\n')
        inputs.append(path)

    for name in structure.get('front', []):
        chapter(name)
    marker('mainmatter')
    number = 0
    for i, part in enumerate(structure['parts'], 1):
        label = f'part:{part["id"]}'
        labels[label] = {'kind': 'part', 'number': roman(i), 'title': part['title']}
        path = gen / f'part-{part["id"]}.md'
        path.write_text(f'::: {{.part #{label}}}\n# {part["title"]}\n\n{part.get("intro", "")}\n:::\n')
        inputs.append(path)
        for name in part['chapters']:
            number += 1
            labels[f'ch:{name}'] = {'kind': 'chapter', 'number': str(number)}
            chapter(name, f'ch:{name}')
    if structure.get('appendices'):
        marker('appendices')
        for i, name in enumerate(structure['appendices']):
            labels[f'app:{name}'] = {'kind': 'appendix', 'number': chr(ord('A') + i)}
            chapter(name, f'app:{name}')
    marker('backmatter')
    for name in structure.get('back', []):
        chapter(name)
    labels_file = gen / 'labels.json'
    labels_file.write_text(json.dumps(labels, indent=1))
    return inputs, labels_file

# Page layouts: B5 (176x250mm) is close to the trim size of most printed
# technical books; A4 and US Letter are for printing at home, with a larger
# font and wide margins to keep lines at a readable length.
layouts = {
    'b5': ['-V', 'papersize=b5', '-V', 'fontsize=10pt', '-V', 'geometry=margin=22mm'],
    'a4': ['-V', 'papersize=a4', '-V', 'fontsize=11pt', '-V', 'geometry=margin=30mm'],
    'letter': ['-V', 'papersize=letter', '-V', 'fontsize=11pt', '-V', 'geometry=margin=30mm'],
}

# Code highlighting themes. 'color' is a restrained traditional scheme: bold
# navy keywords, italic green comments, dark red strings, everything else
# black. 'gray' is for print: bold keywords, italic gray comments.
token_types = ['Alert', 'Annotation', 'Attribute', 'BaseN', 'BuiltIn', 'Char', 'Comment',
               'CommentVar', 'Constant', 'ControlFlow', 'DataType', 'DecVal', 'Documentation',
               'Error', 'Extension', 'Float', 'Function', 'Import', 'Information', 'Keyword',
               'Operator', 'Other', 'Preprocessor', 'RegionMarker', 'SpecialChar',
               'SpecialString', 'String', 'Variable', 'VerbatimString', 'Warning']
keyword_types = ['Keyword', 'ControlFlow', 'DataType']
comment_types = ['Comment', 'CommentVar', 'Documentation', 'Annotation', 'Information', 'Warning']
string_types = ['String', 'Char', 'SpecialChar', 'SpecialString', 'VerbatimString']
themes = {
    'color': {**{k: ('#1a3c8c', True, False) for k in keyword_types},
              **{k: ('#3f7f5f', False, True) for k in comment_types},
              **{k: ('#a31515', False, False) for k in string_types},
              'Preprocessor': ('#1a3c8c', False, False), 'Import': ('#1a3c8c', False, False)},
    'gray': {**{k: (None, True, False) for k in keyword_types},
             **{k: ('#606060', False, True) for k in comment_types}},
}

def theme_file(outdir, name):
    styles = {k: {'text-color': None, 'background-color': None,
                  'bold': False, 'italic': False, 'underline': False} for k in token_types}
    for k, (color, bold, italic) in themes[name].items():
        styles[k].update({'text-color': color, 'bold': bold, 'italic': italic})
    path = outdir / f'{name}.theme'
    path.write_text(json.dumps({'text-color': None, 'background-color': '#f2f2f2',
                                'line-number-color': '#aaaaaa',
                                'line-number-background-color': None,
                                'text-styles': styles}, indent=1))
    return path

def title_art(outdir):
    """The title page's sea star (art/seastar.svg) as SVG, for the HTML, and
    as PDF, for LaTeX (rsvg-convert, Fedora: librsvg2-tools)."""
    svg = outdir / 'seastar.svg'
    shutil.copy(book / 'art' / 'seastar.svg', svg)
    pdf = outdir / 'gen' / 'seastar.pdf'
    subprocess.run(['rsvg-convert', '-f', 'pdf', '-o', pdf, svg], check=True)
    tex = outdir / 'gen' / 'titleart.tex'
    tex.write_text('\\usepackage{graphicx}\n'
                   f'\\newcommand{{\\titleart}}{{\\includegraphics[width=0.5\\linewidth]{{{pdf.resolve()}}}}}\n')
    html = outdir / 'gen' / 'titleart.html'
    html.write_text('<p class="title-art"><img src="seastar.svg" alt="A sea star"></p>\n')
    return tex, html

def build_pdf(inputs, out, paper='b5', gray=False, titlepage=False):
    fonts = []
    if have_tex_file('LibertinusSerif-Regular.otf'):
        fonts += ['-V', 'mainfont=Libertinus Serif']
    else:
        print('note: Libertinus Serif not installed, using Latin Modern', file=sys.stderr)
    if have_tex_file('SourceCodePro-Regular.otf'):
        fonts += ['-V', 'monofont=Source Code Pro', '-V', 'monofontoptions=Scale=MatchLowercase']
    # With a document language set, Pandoc's LaTeX template loads selnolig
    # (Fedora: texlive-selnolig), which suppresses wrong ligatures.
    if not have_tex_file('selnolig.sty'):
        print('note: selnolig.sty not installed, building without a document language',
              file=sys.stderr)
        fonts += ['-M', 'lang=']
    # Number chapters ("Chapter 4"), but not the sections inside them.
    pandoc(inputs, '-o', out, '--pdf-engine=lualatex', '--toc', '--top-level-division=chapter',
           '--number-sections', '-V', 'secnumdepth=0',
           '--highlight-style', theme_file(out.parent, 'gray' if gray else 'color'),
           '-H', style / 'book.tex',
           *(['-H', art_tex, '-H', style / 'titlepage.tex', '-H', style / 'structure.tex']
             if titlepage else []),
           '-V', 'documentclass=scrbook', '-V', 'classoption=open=any,numbers=noenddot',
           *layouts[paper], '-V', 'colorlinks=true',
           *[arg for kind in ('link', 'url', 'file', 'cite')
             for arg in ('-V', f"{kind}color={'black' if gray else '[rgb]{0.1,0.35,0.6}'}")],
           *fonts)

def build_html(inputs, out):
    shutil.copy(style / 'book.css', out.parent / 'book.css')
    pandoc(inputs, '-o', out, '-s', '--toc', '--toc-depth=2', '--css', 'book.css',
           '--number-sections', '--highlight-style', theme_file(out.parent, 'color'))
    if building_book:
        # Put the sea star below the title. (Pandoc's --include-before-body
        # would put it above the title block.)
        page = out.read_text()
        out.write_text(page.replace('</header>', '</header>\n' + art_html.read_text(), 1))

def build_txt(inputs, out):
    pandoc(inputs, '-o', out, '-t', 'plain', '--columns=78', '--number-sections')

parser = argparse.ArgumentParser()
parser.add_argument('--formats', default='pdf,html,txt', help='comma-separated, from: pdf,html,txt')
parser.add_argument('--paper', choices=layouts, default='b5', help='PDF page size (default b5)')
parser.add_argument('--gray', action='store_true', help='grayscale PDF, for print')
parser.add_argument('outdir', type=Path)
parser.add_argument('inputs', nargs='*', type=Path)
args = parser.parse_args()
args.outdir.mkdir(parents=True, exist_ok=True)
building_book = not args.inputs
book_args = []
if args.inputs:
    stem = args.inputs[0].stem
else:
    args.inputs, labels_file = book_inputs(args.outdir / 'gen')
    os.environ['BOOK_LABELS'] = str(labels_file)
    book_args = ['--filter', str(book / 'tools' / 'bookfilter.py')]
    art_tex, art_html = title_art(args.outdir)
    stem = 'book'
for fmt in args.formats.split(','):
    if fmt == 'pdf':
        variant = ('' if args.paper == 'b5' else f'-{args.paper}') + ('-gray' if args.gray else '')
        out = args.outdir / f'{stem}{variant}.pdf'
        build_pdf(args.inputs, out, args.paper, args.gray, titlepage=building_book)
    elif fmt == 'html':
        out = args.outdir / f'{stem}.html'
        build_html(args.inputs, out)
    elif fmt == 'txt':
        out = args.outdir / f'{stem}.txt'
        build_txt(args.inputs, out)
    else:
        parser.error(f'unknown format {fmt}')
    print(out)
