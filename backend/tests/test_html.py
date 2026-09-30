"""Page-text and research-interest extraction on markup patterns seen on real faculty pages."""

from app.ingest.html import html_to_text, own_site_links, scope_prefix, subpage_links
from app.llm.fake import FakeLLM
from app.llm.schemas import PageText

llm = FakeLLM()


def interests(html: str, url: str = "https://x.edu/faculty/jane-doe/") -> str | None:
    return llm.extract_profile([PageText(url=url, text=html_to_text(html))], "Jane Doe", "x.edu").stated_interests


def test_nav_and_skip_links_removed():
    html = """<body><a href="#main">Skip To Main Content</a><nav>Home People Programs Admissions</nav>
    <main><h1>Jane Doe</h1><p>My research focuses on machine learning for medical imaging.</p></main>
    <footer>Copyright University</footer></body>"""
    text = html_to_text(html)
    assert "Skip To" not in text and "Admissions" not in text and "Copyright" not in text
    assert "My research focuses on machine learning for medical imaging." in text


def test_footer_inside_section_is_kept():
    html = """<body><section><header>My Group</header><footer><h2>Looking to join?</h2>
    <p>I am looking for PhD students for the Fall 2026 start cycle.</p></footer></section></body>"""
    assert "looking for PhD students" in html_to_text(html)


def test_source_line_breaks_do_not_split_sentences():
    html = "<p>I am an assistant professor. Our\n   lab does research on probabilistic machine learning.</p>"
    assert "Our lab does research" in html_to_text(html)


def test_research_interests_heading_with_list():
    html = """<main><h2>Research Interests</h2><ul><li>Trustworthy machine learning systems</li>
    <li>Intelligent healthcare systems</li></ul><h2>Awards &amp; Honors</h2><ul><li>Top Reviewer 2025</li></ul></main>"""
    assert interests(html) == "Research interests: Trustworthy machine learning systems; Intelligent healthcare systems."


def test_research_areas_as_spans():
    html = """<div class="research_areas"><span class="detail_label">Research Areas</span>
    <span class="detail_item">Machine learning</span><span class="detail_item">Computational health informatics</span></div>
    <p>Jane Doe received her PhD from Stanford University working on graphical models in 2010 and many other things.</p>"""
    assert interests(html) == "Research interests: Machine learning; Computational health informatics."


def test_unmarked_section_stops_at_known_label():
    html = """<main><h3>Research interests</h3><p>Data mining</p><p>Network science</p><p>Education</p>
    <p>PhD in Computer Science, University of Wisconsin</p></main>"""
    assert interests(html) == "Research interests: Data mining; Network science."


def test_prose_prefers_research_description_over_awards_and_advice():
    html = """<p>I received a Best Paper Award at EMNLP for work on gender bias in language models.</p>
    <p>Undergraduates: if you are interested in doing machine learning research, take CIS 5200 first.</p>
    <p>My research interests span machine learning, optimization, and robustness in healthcare settings.</p>"""
    assert interests(html, "https://x.edu/~jdoe/").startswith("My research interests span")


def test_scope_prefix():
    assert scope_prefix("https://a.github.io/") == "/"
    assert scope_prefix("https://x.edu/~jdoe/index.html") == "/~jdoe/"
    assert scope_prefix("https://x.edu/faculty/jane-doe/") == "/faculty/jane-doe"
    assert scope_prefix("https://x.edu/cse/profiles/doe.html") == "/cse/profiles/doe"


def test_directory_profile_does_not_crawl_department_pages():
    html = """<a href="/about/faculty-hiring/">About</a><a href="/research/areas/">Research</a>
    <a href="/faculty/jane-doe/publications/">Publications</a><a href="https://janedoe.org">Website</a>
    <a href="https://twitter.com/jd">Twitter</a>"""
    base = "https://x.edu/faculty/jane-doe/"
    assert subpage_links(html, base, 8) == ["https://x.edu/faculty/jane-doe/publications/"]
    assert own_site_links(html, base) == ["https://janedoe.org"]
