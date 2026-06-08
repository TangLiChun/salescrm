from app.email_render import markdown_to_html, render_email, render_variables


def test_render_variables_single_brace():
    c = {"org": "ACME", "name": "Sam", "email": "s@a.com", "asn": 15169, "roles": "noc"}
    assert render_variables("Hi {name} at {org} (AS{asn})", c) == "Hi Sam at ACME (AS15169)"
    assert render_variables("{missing}", {}) == "{missing}"  # unknown left as-is


def test_markdown_basic():
    html = markdown_to_html("Hello **bold** and [link](https://x.com)")
    assert "<strong>bold</strong>" in html
    assert '<a href="https://x.com">link</a>' in html
    assert html.startswith("<p>")


def test_markdown_lists_and_escaping():
    html = markdown_to_html("- a\n- b")
    assert html.count("<li>") == 2 and "<ul>" in html
    assert "&lt;script&gt;" in markdown_to_html("<script>")  # html-escaped


def test_render_email_returns_triple():
    tmpl = {"subject": "Hi {name}", "body": "Dear {name},\n\n**Thanks**"}
    subject, text, html = render_email(tmpl, {"name": "Sam"})
    assert subject == "Hi Sam"
    assert text == "Dear Sam,\n\n**Thanks**"  # plain text = md source w/ vars
    assert "<strong>Thanks</strong>" in html
