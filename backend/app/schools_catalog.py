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
    "University of Illinois Urbana-Champaign": {"aliases": ["UIUC", "Illinois", "UIUC CS"], "domain": "illinois.edu"},
    "University of North Carolina at Chapel Hill": {"aliases": ["UNC", "UNC Chapel Hill", "UNC-Chapel Hill"], "domain": "unc.edu"},
    "Texas A&M University": {"aliases": ["TAMU", "Texas A&M", "Texas A and M"], "domain": "tamu.edu"},
    "University of Texas at Austin": {"aliases": ["UT Austin", "UTAustin"], "domain": "utexas.edu"},
    "University of Maryland, College Park": {"aliases": ["UMD", "UMCP", "Maryland"], "domain": "umd.edu"},
    "University of California, Irvine": {"aliases": ["UCI", "UC Irvine"], "domain": "uci.edu"},
    "University of Southern California": {"aliases": ["USC"], "domain": "usc.edu"},
    "New York University": {"aliases": ["NYU"], "domain": "nyu.edu"},
    "University of Pittsburgh": {"aliases": ["Pitt", "UPitt"], "domain": "pitt.edu"},
    "Washington University in St. Louis": {"aliases": ["WashU", "WUSTL"], "domain": "wustl.edu"},
    "University of Virginia": {"aliases": ["UVA"], "domain": "virginia.edu"},
    "Purdue University": {"aliases": ["Purdue"], "domain": "purdue.edu"},
    "University of Wisconsin-Madison": {"aliases": ["UW-Madison", "UW Madison", "Wisconsin"], "domain": "wisc.edu"},
    "California Institute of Technology": {"aliases": ["Caltech"], "domain": "caltech.edu"},
    "University of Chicago": {"aliases": ["UChicago"], "domain": "uchicago.edu"},
    "Rice University": {"aliases": ["Rice"], "domain": "rice.edu"},
    "Emory University": {"aliases": ["Emory"], "domain": "emory.edu"},
    "Vanderbilt University": {"aliases": ["Vanderbilt"], "domain": "vanderbilt.edu"},
    "University of Minnesota": {"aliases": ["UMN"], "domain": "umn.edu"},
    "University of Texas at San Antonio": {"aliases": ["UTSA"], "domain": "utsa.edu"},
    "Arizona State University": {"aliases": ["ASU"], "domain": "asu.edu"},
    "University of Florida": {"aliases": ["UF"], "domain": "ufl.edu"},
    "Mayo Clinic": {"aliases": ["Mayo"], "domain": "mayo.edu"},
}


def builtin_aliases() -> dict[str, str]:
    """lowercase alias (including the full name) -> canonical name."""
    out: dict[str, str] = {}
    for name, info in KNOWN_SCHOOLS.items():
        out[name.lower()] = name
        for alias in info["aliases"]:
            out[alias.lower()] = name
    return out
