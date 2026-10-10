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
    assert [(c.kind, c.claim) for c in x.claims] == [("recruiting", "recruits_generally"), ("contact_policy", "do_not_email")]
    assert x.claims[1].quote.startswith("Because of the volume")
    assert x.email == "myatskar@cis.upenn.edu"


def test_extract_cycle_takes_latest_year():
    page = PageText(url="https://j.github.io/", text=(
        "I am looking for PhD students for the Fall 2025 application / Fall 2026 start cycle. "
        "If you are interested, apply to the CIS PhD Program directly, but do mention me in your application!"
    ))
    x = llm.extract_profile([page], "Jacob Gardner", "upenn.edu")
    claims = {(c.kind, c.claim, c.cycle) for c in x.claims}
    assert ("recruiting", "explicitly_recruiting", "Fall 2026") in claims
    assert ("contact_policy", "apply_via_program", None) in claims


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


def test_postdoc_statements_are_not_phd_recruiting():
    page = PageText(url="https://x.edu/~jd/openpositions.html", text=(
        "We currently have no openings for postdocs. "
        "If you are interested in a postdoc fellowship, please contact me. "
        "I do have one or more openings for PhD students in my research group in the next admission cycle."
    ))
    claims = llm.extract_profile([page], "Jane Doe", "x.edu").claims
    assert [(c.kind, c.claim) for c in claims] == [("recruiting", "explicitly_recruiting")]


def test_visiting_student_statements_are_not_phd_recruiting():
    page = PageText(url="https://x.edu/joining.html", text=(
        "Sorry, I am generally not taking any visiting students from outside of UW. "
        "We are not accepting visiting scholars this year."
    ))
    assert not [c for c in llm.extract_profile([page], "Jane Doe", "x.edu").claims if c.kind == "recruiting"]


@pytest.mark.parametrize("sentence", [
    "Select me as a potential advisor in your application.",
    "If you are interested in our research group, please list Eric Eaton as a prospective advisor in your PhD application and statement of purpose.",
    "If you are interested, please apply here and mention me as a potential advisor.",
    "If you’re interested in working with me, please apply to the Hopkins program and call me out as a potential advisor explaining why.",
])
def test_name_me_as_advisor_means_open_to_students(sentence):
    page = PageText(url="https://x.edu/~ee/", text=sentence)
    claims = {(c.kind, c.claim) for c in llm.extract_profile([page], "Eric Eaton", "x.edu").claims}
    assert claims == {("recruiting", "recruits_generally"), ("contact_policy", "apply_via_program")}


def test_lab_contact_page_roles():
    page = PageText(url="https://lab.x.edu/contact", text=(
        "We are actively recruiting PhD students through the official Graduate Admissions Portal. "
        "If you’re a prospective undergraduate or master’s student interested in our lab, you’re welcome to reach out "
        "directly to Jane, or to any of our PhD students or postdocs. "
        "For academic or clinical collaborations, please contact Jane directly via email."
    ))
    claims = [(c.kind, c.claim) for c in llm.extract_profile([page], "Jane Doe", "x.edu").claims]
    assert claims == [("recruiting", "explicitly_recruiting")]


@pytest.mark.parametrize(("sentence", "expected"), [
    ("We are not currently accepting additional Northeastern graduate students.", "not_recruiting"),
    ("PhD Students: I am not currently directly admitting new PhD students without a fellowship.", "not_recruiting"),
    ("Positions in my group have been filled for this cycle; check back next year for PhD students.", "not_recruiting"),
    ("We have two open positions for PhD students starting Fall 2027.", "explicitly_recruiting"),
    ("We are planning to hire 2~3 PhD students (Fall 2027) who share our passion in ML & Biomedical AI.", "explicitly_recruiting"),
    ("I am also looking for PhD students, especially in but not limited to neural representation learning.", "explicitly_recruiting"),
])
def test_recruiting_phrasings(sentence, expected):
    claims = [c for c in llm.extract_profile([PageText(url="https://x.edu/~a/", text=sentence)], "Ann Lee", "x.edu").claims
              if c.kind == "recruiting"]
    assert [c.claim for c in claims] == [expected]


@pytest.mark.parametrize("sentence, expected", [
    ("If you plan to apply to the PhD program in the CSE department and are interested in working with me, please email me.",
     "welcomes_email"),
    ("Please apply to the PhD program and list me as a potential advisor.", "apply_via_program"),
])
def test_conditional_apply_with_email_invite(sentence, expected):
    page = PageText(url="https://x.edu/~jd/", text=sentence)
    claims = [c for c in llm.extract_profile([page], "Jane Doe", "x.edu").claims if c.kind == "contact_policy"]
    assert [c.claim for c in claims] == [expected]


def test_contacting_an_office_is_not_a_contact_policy():
    page = PageText(url="https://x.edu/~a/", text=(
        "Please contact the CFAR team in the Medical Center Development Office for assistance. "
        "Please contact me by email with your CV."))
    claims = [c.quote for c in llm.extract_profile([page], "Ann Lee", "x.edu").claims]
    assert claims == ["Please contact me by email with your CV."]


def test_hedged_openings_are_no_claim():
    page = PageText(url="https://x.edu/~a/", text="While openings in my research group will be rare, here is what I look for in PhD students.")
    assert [c for c in llm.extract_profile([page], "Ann Lee", "x.edu").claims if c.kind == "recruiting"] == []


def test_may_not_be_able_to_respond_is_do_not_email():
    page = PageText(url="https://x.edu/~a/", text="Due to the high volume of emails, I may not be able to respond to every message.")
    assert [c.claim for c in llm.extract_profile([page], "Ann Lee", "x.edu").claims] == ["do_not_email"]
