"""Formats the markdown a model writes, using plain text elements only.

Model text is never handed to the browser as markup. It is read here into blocks and runs of
text, and each run is shown as a label or, for a web address, a link. Anything this reader
does not recognise, HTML included, stays as the text that was written.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from nicegui import ui

PARAGRAPH = "paragraph"
HEADING = "heading"
ITEM = "item"
CODE = "code"
RULE = "rule"

MAX_INDENT = 3


@dataclass(frozen=True)
class Run:
    """A stretch of text within a line, with how it is to be shown."""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    url: str | None = None
    """Set for a link. Always an http or https address."""

    @property
    def plain(self) -> bool:
        return not (self.bold or self.italic or self.code or self.url)


@dataclass
class Block:
    """A paragraph, heading, list item, block of code or rule."""

    kind: str
    lines: list[list[Run]] = field(default_factory=list)
    level: int = 0
    """For a heading, 1 to 6."""
    marker: str = ""
    """For a list item: a bullet, or its number."""
    indent: int = 0
    """For a list item, how deeply it is nested."""


_INLINE = re.compile(
    r"`(?P<code>[^`\n]+)`"
    r"|\[(?P<label>[^\]\n]+)\]\((?P<target>[^()\s]*(?:\([^()\s]*\)[^()\s]*)*)\)"
    r"|\*\*(?=\S)(?P<bold>.+?)(?<=\S)\*\*"
    r"|(?<!\w)__(?=\S)(?P<bold2>.+?)(?<=\S)__(?!\w)"
    r"|(?<![\w*])\*(?=\S)(?P<italic>[^*\n]+?)(?<=\S)\*(?![\w*])"
    r"|(?<!\w)_(?=\S)(?P<italic2>[^_\n]+?)(?<=\S)_(?!\w)"
    r"|(?P<bare>https?://[^\s<>\"'`]+)",
    re.IGNORECASE,
)
_FENCE = re.compile(r"^\s*```")
_RULE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_ITEM = re.compile(r"^(\s*)(?:([-*+])|(\d+)[.)])\s+(.*)$")
_AFTER_A_LINK = ".,;:!?'\""
_BRACKETS = {")": "(", "]": "[", "}": "{"}


def _is_web_address(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme.lower() in ("http", "https") and bool(parts.hostname)


def _split_bare_link(found: str) -> tuple[str, str]:
    """A bare address and the sentence punctuation that followed it."""
    url = found
    while url and (url[-1] in _AFTER_A_LINK or url[-1] in _BRACKETS):
        opener = _BRACKETS.get(url[-1])
        if opener is not None and url.count(opener) >= url.count(url[-1]):
            break
        url = url[:-1]
    return url, found[len(url) :]


def _runs(text: str) -> list[Run]:
    """One line of text as runs. Marks that do not pair up are left as written."""
    runs: list[Run] = []

    def add(run: Run) -> None:
        if not run.text:
            return
        if runs and runs[-1].plain and run.plain:
            runs[-1] = Run(runs[-1].text + run.text)
        else:
            runs.append(run)

    position = 0
    for match in _INLINE.finditer(text):
        add(Run(text[position : match.start()]))
        position = match.end()
        if match["code"] is not None:
            add(Run(match["code"], code=True))
        elif match["label"] is not None:
            if _is_web_address(match["target"]):
                add(Run(match["label"], url=match["target"]))
            else:
                add(Run(match.group()))
        elif (bold := match["bold"] or match["bold2"]) is not None:
            add(Run(bold, bold=True))
        elif (italic := match["italic"] or match["italic2"]) is not None:
            add(Run(italic, italic=True))
        else:
            url, after = _split_bare_link(match["bare"])
            add(Run(url, url=url) if _is_web_address(url) else Run(url))
            add(Run(after))
    add(Run(text[position:]))
    return runs


def parse(text: str) -> list[Block]:
    """Read markdown into blocks. Never fails: what is not understood is kept as text."""
    blocks: list[Block] = []
    open_block: Block | None = None
    lines = text.split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if _FENCE.match(line):
            body = []
            while index < len(lines) and not _FENCE.match(lines[index]):
                body.append(lines[index])
                index += 1
            index += 1  # the closing fence, if there was one
            blocks.append(Block(CODE, lines=[[Run("\n".join(body))]]))
            open_block = None
        elif not line.strip():
            open_block = None
        elif _RULE.match(line):
            blocks.append(Block(RULE))
            open_block = None
        elif heading := _HEADING.match(line):
            blocks.append(Block(HEADING, level=len(heading[1]), lines=[_runs(heading[2])]))
            open_block = None
        elif item := _ITEM.match(line):
            depth = min((len(item[1].expandtabs(4)) + 1) // 3, MAX_INDENT)
            marker = "•" if item[2] else f"{item[3]}."
            open_block = Block(ITEM, marker=marker, indent=depth, lines=[_runs(item[4])])
            blocks.append(open_block)
        elif open_block is not None and (open_block.kind == PARAGRAPH or line[:1].isspace()):
            open_block.lines.append(_runs(line.strip()))
        else:
            open_block = Block(PARAGRAPH, lines=[_runs(line.strip())])
            blocks.append(open_block)
    return blocks


# -- showing it ---------------------------------------------------------------------------


def _show_run(run: Run, mark: str | None, extra: str) -> None:
    shown: ui.element
    if run.url is not None:
        shown = ui.link(run.text, run.url, new_tab=True).classes(f"mm-link mm-md-run {extra}")
    else:
        style = "".join(
            f" mm-md-{name}" for name in ("bold", "italic", "code") if getattr(run, name)
        )
        shown = ui.label(run.text).classes(f"mm-md-run{style} {extra}")
    if mark:
        shown.mark(mark)


def _show_lines(lines: list[list[Run]], mark: str | None, extra: str = "") -> None:
    if all(len(line) == 1 and line[0].plain for line in lines):
        # Nothing to style: one label holds the lot, line breaks and all.
        label = ui.label("\n".join(line[0].text for line in lines)).classes(f"mm-md-p {extra}")
        if mark:
            label.mark(mark)
        return
    with ui.column().classes("mm-md-lines"):
        for line in lines:
            with ui.element("div").classes("mm-md-line"):
                for run in line:
                    _show_run(run, mark, extra)


def show(text: str, *, mark: str | None = None) -> None:
    """Show a model's markdown as formatted text. `mark` is put on each piece of its text."""
    with ui.column().classes("mm-md"):
        for block in parse(text):
            if block.kind == HEADING:
                level = "mm-md-h mm-md-h" + str(block.level)
                _show_lines(block.lines, mark, level)
            elif block.kind == ITEM:
                with ui.row().classes(f"mm-md-item mm-md-indent-{block.indent}"):
                    ui.label(block.marker).classes("mm-md-marker")
                    with ui.column().classes("mm-md-item-body"):
                        _show_lines(block.lines, mark)
            elif block.kind == CODE:
                code = ui.label(block.lines[0][0].text).classes("mm-md-pre")
                if mark:
                    code.mark(mark)
            elif block.kind == RULE:
                ui.separator().classes("mm-md-rule")
            else:
                _show_lines(block.lines, mark)
