#!/usr/bin/python3 -I
# Pandoc filter for the book, run by tools/build.py. It
#  - replaces references by label with numbers: "[chapter](#ch:coroutines)"
#    becomes "chapter 4", "[appendix](#app:glossary)" becomes "appendix E" and
#    "[Part](#part:io)" becomes "Part IV" (an empty link text gives the
#    lowercase word); a link with any other text keeps its text;
#  - renders the part divisions that build.py inserts (a Div with class
#    "part"): a part page in LaTeX, a heading in the other formats;
#  - switches between front matter, main matter, appendices and back matter
#    at the marker Divs that build.py inserts.
# The numbers come from the JSON file named by the BOOK_LABELS environment
# variable, which build.py writes from metadata.yaml.

import json
import os
import sys
from pandocfilters import (toJSONFilter, stringify, RawBlock, Header, Div, Str,
                           Space, Span)

labels = json.load(open(os.environ['BOOK_LABELS']))
words = {'chapter': 'chapter', 'appendix': 'appendix', 'part': 'Part'}
region = 'front'   # front, main, appendix or back

def latex_escape(s):
    for c in '\\&%$#_{}':
        s = s.replace(c, '\\' + c)
    return s

def reference(content, target):
    label = target[1:]
    if label not in labels:
        sys.exit(f'bookfilter: reference to unknown label "{label}"')
    entry = labels[label]
    text = stringify(content)
    if text and text.lower() != words[entry['kind']].lower():
        return None
    return [Str((text or words[entry['kind']]) + ' ' + entry['number'])]

def part(attr, blocks, fmt):
    label = attr[0]
    entry = labels[label]
    title = stringify(blocks[0]['c'][2]) if blocks and blocks[0]['t'] == 'Header' else entry['title']
    intro = [b for b in blocks if b['t'] != 'Header']
    if fmt == 'latex':
        return ([RawBlock('latex', '\\setpartpreamble[uc][0.72\\linewidth]{\\partintro{}')]
                + intro
                + [RawBlock('latex', '}'),
                   RawBlock('latex', f'\\part{{{latex_escape(title)}}}\\label{{{label}}}')])
    number = Span(['', ['part-number'], []], [Str('Part ' + entry['number'])])
    if fmt.startswith('html'):
        heading = Header(1, [label, ['unnumbered', 'part'], []], [number, Space(), Str(title)])
    else:
        heading = Header(1, [label, ['unnumbered'], []], [Str(f'Part {entry["number"]}: {title}')])
    return [Div(['', ['part-intro'], []], [heading] + intro)]

def action(key, value, fmt, meta):
    global region
    if key == 'Link':
        attr, content, (target, title) = value
        if target.startswith(('#ch:', '#app:', '#part:')):
            new = reference(content, target)
            if new is not None:
                return {'t': 'Link', 'c': [attr, new, [target, title]]}
    elif key == 'Div':
        attr, blocks = value
        classes = attr[1]
        if 'part' in classes:
            return part(attr, blocks, fmt)
        for marker, latex in (('mainmatter', '\\realmainmatter'), ('appendices', '\\appendix'),
                              ('backmatter', '\\backmatter')):
            if marker in classes:
                region = {'mainmatter': 'main', 'appendices': 'appendix', 'backmatter': 'back'}[marker]
                return [RawBlock('latex', latex)] if fmt == 'latex' else []
    elif key == 'Header' and fmt == 'plain' and value[0] == 1 and value[1][0] in labels \
            and labels[value[1][0]]['kind'] == 'chapter':
        # Pandoc's plain-text writer doesn't number headings.
        level, (ident, classes, kvs), content = value
        number = labels[ident]['number']
        return Header(level, [ident, classes, kvs], [Str(f'Chapter {number}:'), Space()] + content)
    elif key == 'Header' and fmt != 'latex' and region != 'main':
        # Outside the main matter, LaTeX numbers (or doesn't number) headings
        # by itself; elsewhere, number nothing, and label appendices by letter.
        level, (ident, classes, kvs), content = value
        if 'unnumbered' not in classes:
            classes = classes + ['unnumbered']
            if level == 1 and ident in labels and labels[ident]['kind'] == 'appendix':
                content = [Str(f'Appendix {labels[ident]["number"]}:'), Space()] + content
            return Header(level, [ident, classes, kvs], content)

if __name__ == '__main__':
    toJSONFilter(action)
