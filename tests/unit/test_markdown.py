"""Reading the markdown a model writes into blocks and styled runs of text."""

from manyminds.ui.markdown import Block, Run, parse


def plain(text: str) -> Run:
    return Run(text)


def test_plain_text_is_one_paragraph_with_its_line_breaks_kept() -> None:
    assert parse("First line,\nsecond line.") == [
        Block("paragraph", lines=[[plain("First line,")], [plain("second line.")]])
    ]


def test_blank_lines_separate_paragraphs() -> None:
    assert [block.lines for block in parse("One.\n\n\nTwo.")] == [
        [[plain("One.")]],
        [[plain("Two.")]],
    ]


def test_headings_carry_their_level() -> None:
    assert parse("## Research notes\n### Useful sources") == [
        Block("heading", level=2, lines=[[plain("Research notes")]]),
        Block("heading", level=3, lines=[[plain("Useful sources")]]),
    ]


def test_bold_italic_and_code_are_marked_within_a_line() -> None:
    (block,) = parse("A **bold** claim, an *aside*, and `code_here`.")

    assert block.lines == [
        [
            plain("A "),
            Run("bold", bold=True),
            plain(" claim, an "),
            Run("aside", italic=True),
            plain(", and "),
            Run("code_here", code=True),
            plain("."),
        ]
    ]


def test_bullets_and_numbers_become_list_items_with_their_marker() -> None:
    assert parse("- first\n* second\n3. third\n4) fourth") == [
        Block("item", marker="•", lines=[[plain("first")]]),
        Block("item", marker="•", lines=[[plain("second")]]),
        Block("item", marker="3.", lines=[[plain("third")]]),
        Block("item", marker="4.", lines=[[plain("fourth")]]),
    ]


def test_indented_lines_continue_the_item_above_and_nested_items_keep_their_depth() -> None:
    text = "1. **Source:** https://a.example/p\n   **Title:** A page\n   - nested point\n\nAfter."

    assert parse(text) == [
        Block(
            "item",
            marker="1.",
            lines=[
                [
                    Run("Source:", bold=True),
                    plain(" "),
                    Run("https://a.example/p", url="https://a.example/p"),
                ],
                [Run("Title:", bold=True), plain(" A page")],
            ],
        ),
        Block("item", marker="•", indent=1, lines=[[plain("nested point")]]),
        Block("paragraph", lines=[[plain("After.")]]),
    ]


def test_links_keep_their_text_and_address_and_bare_addresses_link_to_themselves() -> None:
    (block,) = parse("See [the archive](https://archive.example/a?b=1) or https://b.example/c.")

    assert block.lines == [
        [
            plain("See "),
            Run("the archive", url="https://archive.example/a?b=1"),
            plain(" or "),
            Run("https://b.example/c", url="https://b.example/c"),
            plain("."),
        ]
    ]


def test_a_link_that_is_not_a_web_address_stays_as_the_text_that_was_written() -> None:
    (block,) = parse(
        "[click](javascript:alert(1)) and [x](data:text/html,hi) and [y](//evil.example)"
    )

    assert all(run.url is None for line in block.lines for run in line)
    assert "".join(run.text for run in block.lines[0]) == (
        "[click](javascript:alert(1)) and [x](data:text/html,hi) and [y](//evil.example)"
    )


def test_html_is_just_text() -> None:
    (block,) = parse('<img src=x onerror="alert(1)"> <script>alert(1)</script>')

    assert block.lines == [[plain('<img src=x onerror="alert(1)"> <script>alert(1)</script>')]]


def test_an_image_is_not_loaded_only_linked() -> None:
    (block,) = parse("![a chart](https://evil.example/?leak=1)")

    assert block.lines == [[plain("!"), Run("a chart", url="https://evil.example/?leak=1")]]


def test_a_fenced_block_is_kept_exactly_and_nothing_in_it_is_styled() -> None:
    assert parse("Before\n```python\nx = **1**\n  y = 2\n```\nAfter") == [
        Block("paragraph", lines=[[plain("Before")]]),
        Block("code", lines=[[plain("x = **1**\n  y = 2")]]),
        Block("paragraph", lines=[[plain("After")]]),
    ]


def test_a_rule_separates_and_unfinished_marks_are_left_as_written() -> None:
    assert parse("One **unfinished\n---\n2 * 3 * 4 and snake_case_name") == [
        Block("paragraph", lines=[[plain("One **unfinished")]]),
        Block("rule"),
        Block("paragraph", lines=[[plain("2 * 3 * 4 and snake_case_name")]]),
    ]


def test_empty_text_has_no_blocks() -> None:
    assert parse("  \n\n ") == []
