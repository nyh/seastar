# Asynchronous Programming with Seastar

This directory holds the source of the book *Asynchronous Programming with
Seastar*, and the tools that build it.

- `PLAN.md`: the book's plan (table of contents, decisions, open questions).
- `metadata.yaml`: the title page's text, and the book's structure: which
  chapters it has, in which order, grouped in parts, followed by the
  appendices and the back matter.
- `chapters/`: one Markdown file per chapter, named after its subject
  (`coroutines.md`), never its number.
- `tools/build.py`: builds PDF, HTML and plain text.
- `tools/bookfilter.py`: the Pandoc filter that numbers chapters, renders the
  parts, and resolves references.
- `tools/check_overlap.py`: reports text copied word for word from other
  documents.
- `style/`: the LaTeX preamble (`book.tex`), the title page and part pages
  (`titlepage.tex`, `structure.tex`), and the HTML stylesheet (`book.css`).
- `art/seastar.svg`: the sea star on the title page, in a stippled
  pen-and-ink style. It was drawn by `art/seastar.py`, which the build does
  not run; run it only to make a new version deliberately.
- `research/`: the API coverage audit used to plan the book, and notes
  backing facts used in the text.

## Writing

Chapters are numbered by their position in `metadata.yaml`, so adding,
removing or moving a chapter means editing that list, and nothing else.

Each chapter file starts with a heading labeled after the file name:
`# Coroutines {#ch:coroutines}` in `chapters/coroutines.md`, or
`{#app:glossary}` for an appendix. Parts are labeled `part:` followed by
their `id` in `metadata.yaml`.

Never write a chapter number by hand. Refer to a chapter by its label, and
the build supplies the number:

| You write | The book shows |
|---|---|
| `[chapter](#ch:coroutines)` | chapter 4 |
| `[Chapter](#ch:coroutines)` | Chapter 4 |
| `[appendix](#app:glossary)` | appendix E |
| `[Part](#part:io)` | Part IV |
| `[the next chapter](#ch:time)` | the next chapter (a link, without a number) |

A reference to a label that doesn't exist stops the build.

## Building

    tools/build.py build INPUT.md...

By default this writes three files into `build/`:

- `INPUT.pdf`: the book edition. Its pages are B5 (176×250 mm), close to
  the size of most printed technical books, with code highlighted in color.
- `INPUT.html`: a single web page.
- `INPUT.txt`: plain text.

### Options

| Option | Effect |
|---|---|
| `--formats LIST` | Build only some outputs. `LIST` is a comma-separated subset of `pdf`, `html` and `txt`. |
| `--paper a4` | PDF on A4 pages, for printing at home. It uses an 11 pt font and wide margins, so lines stay at a readable length. Output: `INPUT-a4.pdf`. |
| `--paper letter` | The same on US Letter pages. Output: `INPUT-letter.pdf`. |
| `--gray` | Grayscale PDF for black-and-white printing, or for a publisher. Keywords are bold, comments italic gray, and links black. Output: `INPUT-gray.pdf`. |

`--paper` and `--gray` affect only the PDF, and they can be combined.
For example, to print the book at home on a black-and-white printer:

    tools/build.py --formats pdf --paper a4 --gray build INPUT.md

This writes `build/INPUT-a4-gray.pdf`.

The color theme is deliberately restrained: bold navy keywords, italic
green comments and dark red strings, with everything else black. The
HTML always uses it. Both themes are defined in `tools/build.py`.

## Prerequisites

The build needs Pandoc, its Python filter library, and LuaLaTeX with a few
LaTeX packages and fonts. On Fedora:

    sudo dnf install pandoc-cli pandoc-pdf python3-pandocfilters \
        texlive-koma-script texlive-microtype \
        texlive-libertinus-fonts texlive-libertinus-otf texlive-sourcecodepro \
        texlive-framed texlive-tcolorbox texlive-upquote texlive-fvextra \
        texlive-selnolig librsvg2-tools

`pandoc-pdf` pulls in LuaLaTeX and the basic LaTeX collection. The other
packages are:

| Package | Used for |
|---|---|
| `pandoc-cli` | Pandoc itself |
| `pandoc-pdf` | PDF output (requires LaTeX) |
| `python3-pandocfilters` | the book's Pandoc filters, written in Python |
| `texlive-koma-script` | the `scrbook` document class and page headers |
| `texlive-microtype` | better justification and spacing |
| `texlive-libertinus-fonts`, `texlive-libertinus-otf` | the text font, Libertinus Serif |
| `texlive-sourcecodepro` | the code font, Source Code Pro |
| `texlive-framed` | shaded, highlighted code blocks |
| `texlive-tcolorbox` | note and warning boxes |
| `texlive-upquote` | straight quotes in code |
| `texlive-fvextra` | wrapping long code lines |
| `librsvg2-tools` | `rsvg-convert`, which turns the title page's drawing into PDF |
| `texlive-selnolig` | suppressing ligatures that are wrong in English, such as the "fl" in "halflife" |

Without the two fonts, `build.py` falls back to LaTeX's default font,
Latin Modern. The other packages are required.

## Tools for the example application

The book's example program, Shoal, speaks the Redis protocol, so it is
used with the standard Redis tools. Fedora packages them as Valkey, the
compatible open-source fork of Redis:

    sudo dnf install valkey python3-redis

| Package | Used for |
|---|---|
| `valkey` | `valkey-cli` to talk to Shoal, `valkey-benchmark` to load it, and `valkey-server` to compare against it |
| `python3-redis` | the Python Redis client (redis-py), used by Shoal's test suite |

The optional `valkey-compat-redis` package adds the traditional names
(`redis-cli`, `redis-benchmark`). The `memtier_benchmark` load generator,
used in a few benchmarks, is not packaged by Fedora. To run those
benchmarks, build it from source (https://github.com/RedisLabs/memtier_benchmark).
