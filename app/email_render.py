from __future__ import annotations

import html as _html
import re


def render_variables(text: str, contact: dict) -> str:
    asn = str(contact.get("asn") or "")
    return (
        str(text or "")
        .replace("{org}", str(contact.get("org") or ""))
        .replace("{name}", str(contact.get("name") or ""))
        .replace("{email}", str(contact.get("email") or ""))
        .replace("{asn}", asn)
        .replace("{roles}", str(contact.get("roles") or ""))
    )


def _inline(text: str) -> str:
    out = _html.escape(text)
    out = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r'<a href="\2">\1</a>', out)
    return out


def markdown_to_html(text: str) -> str:
    out: list[str] = []
    list_tag: str | None = None

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            out.append("</ul>" if list_tag == "ul" else "</ol>")
            list_tag = None

    for raw in str(text or "").split("\n"):
        line = raw.rstrip()
        m_ul = re.match(r"^[-*]\s+(.+)", line)
        m_ol = re.match(r"^\d+\.\s+(.+)", line)
        m_h = re.match(r"^(#{1,3})\s+(.+)", line)
        if m_ul:
            if list_tag != "ul":
                close_list()
                out.append("<ul>")
                list_tag = "ul"
            out.append(f"<li>{_inline(m_ul.group(1))}</li>")
        elif m_ol:
            if list_tag != "ol":
                close_list()
                out.append("<ol>")
                list_tag = "ol"
            out.append(f"<li>{_inline(m_ol.group(1))}</li>")
        elif m_h:
            close_list()
            level = len(m_h.group(1))
            out.append(f"<h{level}>{_inline(m_h.group(2))}</h{level}>")
        elif line.strip() == "":
            close_list()
        else:
            close_list()
            out.append(f"<p>{_inline(line)}</p>")
    close_list()
    return "".join(out)


def render_email(template: dict, contact: dict) -> tuple[str, str, str]:
    """Return (subject, plain_text, html). Plain text is the variable-substituted
    Markdown source (readable as-is); html is the rendered version."""
    subject = render_variables(template.get("subject", ""), contact)
    text = render_variables(template.get("body", ""), contact)
    return subject, text, markdown_to_html(text)
