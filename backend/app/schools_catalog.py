"""Built-in school names, aliases and domains, so common shorthand like
"UPenn" works without asking. Schools not listed here are confirmed once by
the user and saved to the database.
"""

KNOWN_SCHOOLS: dict[str, dict] = {
    "University of Pennsylvania": {"aliases": ["UPenn", "Penn", "U Penn", "U of Penn"], "domain": "upenn.edu"},
    "Northeastern University": {"aliases": ["Northeastern", "NEU"], "domain": "northeastern.edu"},
    "Massachusetts Institute of Technology": {"aliases": ["MIT"], "domain": "mit.edu"},
    "Stanford University": {"aliases": ["Stanford"], "domain": "stanford.edu"},
    "Harvard University": {"aliases": ["Harvard", "HMS", "Harvard Medical School"], "domain": "harvard.edu"},
    "Carnegie Mellon University": {"aliases": ["CMU", "Carnegie Mellon"], "domain": "cmu.edu"},
    "Johns Hopkins University": {"aliases": ["JHU", "Johns Hopkins", "Hopkins"], "domain": "jhu.edu"},
    "Columbia University": {"aliases": ["Columbia"], "domain": "columbia.edu"},
    "University of California, Berkeley": {"aliases": ["UC Berkeley", "Berkeley", "UCB"], "domain": "berkeley.edu"},
    "University of California, San Francisco": {"aliases": ["UCSF"], "domain": "ucsf.edu"},
    "University of California, Los Angeles": {"aliases": ["UCLA"], "domain": "ucla.edu"},
    "University of California, San Diego": {"aliases": ["UCSD", "UC San Diego"], "domain": "ucsd.edu"},
    "University of Washington": {"aliases": ["UW", "UWashington", "U Washington"], "domain": "washington.edu"},
    "Duke University": {"aliases": ["Duke"], "domain": "duke.edu"},
    "Yale University": {"aliases": ["Yale"], "domain": "yale.edu"},
    "Cornell University": {"aliases": ["Cornell", "Cornell Tech"], "domain": "cornell.edu"},
    "Princeton University": {"aliases": ["Princeton"], "domain": "princeton.edu"},
    "University of Michigan": {"aliases": ["UMich", "Michigan", "U Michigan"], "domain": "umich.edu"},
    "Georgia Institute of Technology": {"aliases": ["Georgia Tech", "GaTech", "GT"], "domain": "gatech.edu"},
    "Boston University": {"aliases": ["BU"], "domain": "bu.edu"},
    "Brown University": {"aliases": ["Brown"], "domain": "brown.edu"},
    "Northwestern University": {"aliases": ["Northwestern"], "domain": "northwestern.edu"},
    "University of Toronto": {"aliases": ["UofT", "U of T", "Toronto"], "domain": "utoronto.ca"},
}


def builtin_aliases() -> dict[str, str]:
    """lowercase alias (including the full name) -> canonical name."""
    out: dict[str, str] = {}
    for name, info in KNOWN_SCHOOLS.items():
        out[name.lower()] = name
        for alias in info["aliases"]:
            out[alias.lower()] = name
    return out
