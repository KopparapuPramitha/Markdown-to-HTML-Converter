"""
converter.py
A lightweight Markdown -> HTML converter with no external dependencies.

Supports:
- Headers (# through ######)
- Bold (**text** or __text__) and italic (*text* or _text_)
- Inline code (`code`) and fenced code blocks (```lang ... ```)
- Links [text](url) and images ![alt](url) with safe attribute escaping
- Unordered lists (-, *, +) and ordered lists (1. 2. ...) including nested lists
- Blockquotes (> text)
- Horizontal rules (---, ***, ___)
- Paragraphs (blank-line separated)

This is a deliberately compact implementation covering common Markdown
syntax — not a full CommonMark implementation.
"""

import html
import re
from typing import List, Optional, Tuple

HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")
HR_RE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
UL_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
OL_RE = re.compile(r"^(\s*)\d+\.\s+(.*)$")
BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")
FENCE_RE = re.compile(r"^```([^\s`]*)\s*$")

INLINE_CODE_RE = re.compile(r"`([^`]+)`")
BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1")
ITALIC_RE = re.compile(r"(\*|_)(.+?)\1")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)")


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def _escape_attr(text: str) -> str:
    return html.escape(text, quote=True)


def _inline(text: str) -> str:
    """Apply inline-level transformations: code, images, links, bold, italic."""
    placeholders: List[str] = []

    def stash_code(match: "re.Match") -> str:
        placeholders.append(_escape(match.group(1)))
        return f"\x00{len(placeholders) - 1}\x00"

    text = INLINE_CODE_RE.sub(stash_code, text)
    text = _escape(text)

    def render_image(m: "re.Match") -> str:
        alt = _escape_attr(html.unescape(m.group(1)))
        src = _escape_attr(html.unescape(m.group(2)))
        title = (
            f' title="{_escape_attr(html.unescape(m.group(3)))}"'
            if m.group(3)
            else ""
        )
        return f'<img src="{src}" alt="{alt}"{title}>'

    def render_link(m: "re.Match") -> str:
        label = m.group(1)
        href = _escape_attr(html.unescape(m.group(2)))
        title = (
            f' title="{_escape_attr(html.unescape(m.group(3)))}"'
            if m.group(3)
            else ""
        )
        return f'<a href="{href}"{title}>{label}</a>'

    text = IMAGE_RE.sub(render_image, text)
    text = LINK_RE.sub(render_link, text)
    text = BOLD_RE.sub(r"<strong>\2</strong>", text)
    text = ITALIC_RE.sub(r"<em>\2</em>", text)

    def restore_code(match: "re.Match") -> str:
        idx = int(match.group(1))
        return f"<code>{placeholders[idx]}</code>"

    text = re.sub(r"\x00(\d+)\x00", restore_code, text)
    return text


def markdown_to_html(markdown_text: str) -> str:
    """Convert a Markdown string to an HTML fragment."""
    lines = markdown_text.splitlines()
    html_lines: List[str] = []

    i = 0
    paragraph_buffer: List[str] = []
    # Tracks active list levels as (tag, indent_width)
    list_stack: List[Tuple[str, int]] = []

    def flush_paragraph() -> None:
        if paragraph_buffer:
            joined = " ".join(paragraph_buffer)
            html_lines.append(f"<p>{_inline(joined)}</p>")
            paragraph_buffer.clear()

    def close_lists(target_indent: int = -1) -> None:
        while list_stack and list_stack[-1][1] > target_indent:
            tag, _ = list_stack.pop()
            html_lines.append(f"</{tag}>")

    def handle_list_item(tag: str, indent_str: str, content: str) -> None:
        indent = len(indent_str.replace("\t", "    "))
        if not list_stack:
            html_lines.append(f"<{tag}>")
            list_stack.append((tag, indent))
        elif indent > list_stack[-1][1]:
            html_lines.append(f"<{tag}>")
            list_stack.append((tag, indent))
        else:
            close_lists(indent)
            if not list_stack or list_stack[-1][0] != tag:
                if list_stack and list_stack[-1][1] == indent:
                    old_tag, _ = list_stack.pop()
                    html_lines.append(f"</{old_tag}>")
                html_lines.append(f"<{tag}>")
                list_stack.append((tag, indent))
        html_lines.append(f"<li>{_inline(content)}</li>")

    while i < len(lines):
        line = lines[i]

        # Fenced code block
        fence_match = FENCE_RE.match(line)
        if fence_match:
            flush_paragraph()
            close_lists()
            lang = fence_match.group(1)
            code_lines = []
            i += 1
            while i < len(lines) and not FENCE_RE.match(lines[i]):
                code_lines.append(lines[i])
                i += 1
            code_html = _escape("\n".join(code_lines))
            lang_attr = f' class="language-{_escape_attr(lang)}"' if lang else ""
            html_lines.append(f"<pre><code{lang_attr}>{code_html}</code></pre>")
            i += 1
            continue

        # Blank line -> paragraph/list break
        if line.strip() == "":
            flush_paragraph()
            close_lists()
            i += 1
            continue

        # Horizontal rule
        if HR_RE.match(line):
            flush_paragraph()
            close_lists()
            html_lines.append("<hr>")
            i += 1
            continue

        # Header
        header_match = HEADER_RE.match(line)
        if header_match:
            flush_paragraph()
            close_lists()
            level = len(header_match.group(1))
            content = _inline(header_match.group(2).strip())
            html_lines.append(f"<h{level}>{content}</h{level}>")
            i += 1
            continue

        # Blockquote
        bq_match = BLOCKQUOTE_RE.match(line)
        if bq_match:
            flush_paragraph()
            close_lists()
            quote_lines = [bq_match.group(1)]
            i += 1
            while i < len(lines) and BLOCKQUOTE_RE.match(lines[i]):
                quote_lines.append(BLOCKQUOTE_RE.match(lines[i]).group(1))
                i += 1
            inner = markdown_to_html("\n".join(quote_lines))
            html_lines.append(f"<blockquote>{inner}</blockquote>")
            continue

        # Unordered list
        ul_match = UL_RE.match(line)
        if ul_match:
            flush_paragraph()
            handle_list_item("ul", ul_match.group(1), ul_match.group(2))
            i += 1
            continue

        # Ordered list
        ol_match = OL_RE.match(line)
        if ol_match:
            flush_paragraph()
            handle_list_item("ol", ol_match.group(1), ol_match.group(2))
            i += 1
            continue

        # Otherwise: part of a paragraph
        close_lists()
        paragraph_buffer.append(line.strip())
        i += 1

    flush_paragraph()
    close_lists()

    return "\n".join(html_lines)


def wrap_html_document(
    body: str, title: str = "Document", css: Optional[str] = None
) -> str:
    """Wrap an HTML fragment in a full standalone HTML document."""
    style_tag = f"<style>\n{css}\n</style>" if css else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_escape(title)}</title>
{style_tag}
</head>
<body>
{body}
</body>
</html>
"""
