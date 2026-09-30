import pytest

from app.llm.fake import FakeLLM
from app.llm.schemas import PageText, StructuredProfile
from app.schools_catalog import builtin_aliases

llm = FakeLLM()
ALIASES = builtin_aliases()


@pytest.mark.parametrize(
    ("line", "name", "school", "dept", "url"),
    [
        ("Jacob Gardner (UPenn CIS)", "Jacob Gardner", "UPenn", "CIS", None),
        ("Mark Yatskar, UPenn", "Mark Yatskar", "UPenn", None, None),
        ("Eric Eaton - University of Pennsylvania, Computer Science", "Eric Eaton", "University of Pennsylvania",
         "Computer Science", None),
        ("Pranam Chatterjee UPenn Bioengineering https://www.chatterjeelab.com/", "Pranam Chatterjee", "UPenn",
         "Bioengineering", "https://www.chatterjeelab.com/"),
        ("Li Shen, Penn Medicine", "Li Shen", "Penn", "Medicine", None),
        ("Jane Doe, Some Unknown University", "Jane Doe", "Some Unknown University", None, None),
    ],
)
def test_parse_formats(line, name, school, dept, url):
    [e] = llm.parse_professor_input(line, ALIASES)
    assert (e.name, e.school_raw, e.department_raw, e.url) == (name, school, dept, url)
    assert e.issues == []


def test_parse_semicolons_and_header():
    entries = llm.parse_professor_input("UPenn:\nJacob Gardner\nMark Yatskar; Eric Wong", ALIASES)
    assert [(e.name, e.school_raw) for e in entries] == [
        ("Jacob Gardner", "UPenn"), ("Mark Yatskar", "UPenn"), ("Eric Wong", "UPenn"),
    ]


def test_parse_flags_missing_school_instead_of_guessing():
    [e] = llm.parse_professor_input("Jacob Gardner", ALIASES)
    assert e.school_raw is None and "missing_school" in e.issues


def test_normalize_school():
    info = llm.normalize_school("UPenn")
    assert info.name == "University of Pennsylvania" and info.primary_domain == "upenn.edu" and info.known
    assert not llm.normalize_school("Nowhere College").known


def test_extract_recruiting_and_contact_policy():
    home = PageText(url="https://x.upenn.edu/", text=(
        "Mark Yatskar is an Assistant Professor in the Department of Computer and Information Science.\n"
        "My research focuses on vision and language and medical imaging.\n"
        "Every year, I am looking for at least one new PhD student.\n"
        "Because of the volume of requests, I cannot respond to email from prospective PhD students.\n"
        "Contact: myatskar [at] cis [dot] upenn [dot] edu"
    ))
    x = llm.extract_profile([home], "Mark Yatskar", "upenn.edu")
    assert x.title == "Assistant Professor"
    assert x.recruiting_status == "recruits_generally"
    assert x.contact_policy == "do_not_email"
    assert x.contact_evidence.quote.startswith("Because of the volume")
    assert x.email == "myatskar@cis.upenn.edu"


def test_extract_cycle_takes_latest_year():
    page = PageText(url="https://j.github.io/", text=(
        "I am looking for PhD students for the Fall 2025 application / Fall 2026 start cycle. "
        "If you are interested, apply to the CIS PhD Program directly, but do mention me in your application!"
    ))
    x = llm.extract_profile([page], "Jacob Gardner", "upenn.edu")
    assert x.recruiting_status == "explicitly_recruiting"
    assert x.recruiting_cycle == "Fall 2026"
    assert x.contact_policy == "apply_via_program"


def test_screen_labels():
    profile = StructuredProfile(methods=["deep learning"], domains=["medical imaging", "radiology"])
    strong = llm.screen_professor(profile, [], None, "Deep learning for radiology and medical imaging.")
    none = llm.screen_professor(profile, [], None, "Cryptography and zero-knowledge proofs.")
    assert strong.label == "strong" and none.label == "no"


def test_screen_generic_terms_alone_are_not_strong():
    profile = StructuredProfile(methods=["machine learning", "optimization"], domains=["healthcare", "ehr"])
    generic = llm.screen_professor(profile, [], None, "Probabilistic machine learning and Bayesian optimization.")
    assert generic.label == "no"


def test_screen_synonyms_and_related_fields():
    profile = StructuredProfile(methods=["machine learning"], domains=["healthcare", "ehr"])
    ehr = llm.screen_professor(profile, [], None, "AI for public health using electronic health records.")
    assert ehr.label in ("possible", "strong") and "ehr" in ehr.reason
