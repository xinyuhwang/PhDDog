# PhDDog — Decision Log

Why PhDDog works the way it does. Each entry records the decision, why it
was made, what was rejected, and what follows from it. The current design is
in [DESIGN.md](DESIGN.md); this file explains how it got there.

Entries are grouped by topic. Dates are when the decision was made (2026).
To change a decision, add a new entry that supersedes it rather than editing
the old one.

---

## Product scope

### D1. A four-stage funnel where the user decides at every step (Sep 29)

**Decision.** Add & resolve professors → screen → deep-dive into papers →
outreach. The app suggests at each stage; the user pins, picks papers, edits
emails and sends them.

**Why.** The decisions (who to contact, what to say) are personal and high
stakes. Automation is most useful for gathering and checking facts.

**Rejected.** Fully automated outreach; sending email from the app.

**Consequences.** No email integration in the MVP. Every generated artifact
is editable and versioned. The outreach log records what was actually sent.

### D2. The user supplies professor names; no faculty-directory scraping (Sep 29)

**Decision.** Professors are added by typing `Name, School` in free form
(any order, separators or nicknames). The app finds and reads each
professor's own site.

**Why.** Department directories don't say who is recruiting. Scraping them
needs a scraper per school, which breaks whenever a page changes. Typing
names costs the user little, and the user already knows who they care about.

**Rejected.** Scraping faculty listing pages (the original v0.1 design).

**Consequences.** Nothing is school-specific; adding a school costs nothing.
Finding homepages needs either web search or a pasted URL (D4).

### D3. The user supplies papers (PDF or link); no Google Scholar scraping (Sep 29)

**Decision.** For a pinned professor, the user uploads PDFs or pastes
links. Metadata comes from arXiv, PubMed, Crossref and Unpaywall.

**Why.** Google Scholar has no API, blocks automation quickly and prohibits
scraping. Letting the user choose papers also keeps the analysis focused on
the work they care about.

**Rejected.** Scraping Scholar profiles; using a paid Scholar proxy.

---

## Architecture

### D4. Stack: FastAPI + Next.js + Postgres, run locally with Docker Compose (Sep 29)

**Decision.** Python backend (FastAPI, SQLAlchemy, Alembic), a DB-backed job
queue with a worker process, a Next.js + TypeScript frontend, and Postgres 16
with pgvector. Everything runs locally.

**Why.** Python has the best tools for PDFs, HTML and LLMs. One database
holds both relational data and future embeddings. A job table is enough at
this scale (hundreds of professors). Running locally keeps the resume and
emails private.

**Rejected.** Celery/RQ (not needed yet); a hosted deployment (not needed
for a single user).

**Consequences.** No logins or accounts. The data model still carries
`user_id`, so multiple users can be added later.

### D5. Offline-first: rule-based stand-ins instead of a model by default (Sep 30)

**Decision.** `LLM_PROVIDER=fake` is the default. It is a rule-based
implementation of every model task: parsing, extraction, screening,
summaries, connections and email templates. Anything it generates (rather
than quotes) is marked `[FAKE]` or "rule-based".

**Why.** The app should be buildable, testable and usable without an API
key or cost. Tests are deterministic.

**Consequences.** Offline quality is limited for judgment tasks, which
drives D16 (hiding research fit) and D22 (analyses written in-session). The
`claude` and `ollama` providers plug into the same interface.

### D6. Code decides; models only extract and write (Sep 30)

**Decision.** Fetching, parsing, deduplication, dates, source
classification, recruiting status and confidence are all deterministic code.
Models (or the offline rules) only *find and quote* statements and *write*
summaries, connections and emails.

**Why.** Code is reproducible, testable and cheap. A model that sets a
status directly can't be audited.

**Consequences.** Status and confidence can be recomputed at any time from
stored evidence (D9).

### D7. Model choice: Claude for judgment tasks; local models tested for extraction (Sep 30 – Oct 1)

**Decision.** Claude (`claude-opus-5-5`, with per-task effort) is the
planned provider for analysis and writing. An `ollama` provider exists for
extraction. Embeddings were deferred: at this scale, screening can be done
directly.

**Evidence.** `llama3.2` (3B) was compared with the rules on the 15
hand-checked professors. It returned 25 recruiting/contact statements: 5
correct, **12 invented** (11 copied from the example sentences in the
prompt), 7 empty, and it missed 3 real statements. It also cut research
interest lists down to their first item.

**Decision (follow-up).** Keep the rules for recruiting and contact
statements. Evaluate a larger local model (8B) or Claude for summaries,
connection points and emails, the tasks rules can't do, rather than for
extraction.

**Rejected.** FLAN-T5-large: short input window, unreliable structured
output, weak at long documents and writing.

---

## Trust and grounding

### D8. Every quote must appear verbatim in its source (Sep 30, extended Oct 1–2)

**Decision.** Any statement shown as evidence (recruiting, contact policy,
connection points, imported analyses) must quote its source word for word.
The quote must be at least 15 characters and is checked against the stored
page, paper or resume text, with whitespace normalized. Quotes that fail
are dropped (pipeline) or rejected with an error (API).

**Why.** Models invent plausible quotes (D7). An empty string "appears" in
every page, which is how the 15-character minimum came about.

**Consequences.** Fabricated claims never reach the UI. Paraphrases are
rejected too, so the user must copy and paste exact sentences.

### D9. Recruiting evidence is stored as rows with history; status is computed (Oct 1)

**Decision.** Each recruiting or contact-policy statement is an `evidence`
row with: quote, source URL, source type (personal / lab / faculty profile /
admissions), cycle named, the page's "last updated" date, first and last
seen, and `gone_at`. A professor's status and confidence are computed from
current rows.

- **High confidence:** an explicit statement naming the target cycle (or
  later), on the professor's own page.
- **Medium:** their own page, but undated or general.
- **Low:** an earlier cycle, or not their own page.

**Why.** One flat quote per professor lost history and provenance and
couldn't express confidence.

**Consequences.** Missing evidence is shown as **"No recruiting evidence
found"** or **"Only older evidence"** with the last-checked date, never as
"not recruiting". Checks older than 60 days are flagged. A statement is
marked gone only if its page was actually re-read without it, or the page
was dropped from a crawl that had no failures.

### D10. How common phrasings are interpreted (Oct 1–2)

These rules were each learned from a real faculty page:

| Phrasing | Interpretation | Learned from |
| --- | --- | --- |
| "apply … and list/name/select/call me (out) as an advisor" | **Open to students** (medium), plus *apply via program* | Wong, Eaton, Yatskar, Saria |
| An undated invitation on the same page as a dated statement | Part of the dated statement; it does not make an old cycle current | Gardner |
| Statements about postdocs, undergrads, master's students or collaborators | Ignored for PhD status and contact policy | Eaton, Unberath |
| "openings will be rare / limited / unlikely" | No claim either way ("not limited to" is not a hedge) | Koyejo, Althoff |
| "not (currently) (directly) accepting / admitting …" | Not recruiting | Sathyanarayana, Washington |
| "please contact [an office]" | Not a contact policy; only "contact me / us / Dr. X" counts | Gevaert pages |
| "planning to hire", "may not be able to respond" | Recruiting; don't email | R. Liu |

---

## Crawling

### D11. Crawl the professor's own corner of the web, prioritizing recruiting pages (Sep 30 – Oct 1)

**Decision.**
- Stay within the profile's path prefix. A directory profile like
  `/faculty/jane-doe/` doesn't wander into department-wide pages.
- Follow "Website / Homepage / Lab" links off a directory profile and explore
  that site like a homepage.
- From a personal site, follow up to 2 lab-site links.
- Prioritize "Open positions / Join / Prospective / Contact" links, and
  follow them one extra hop from subpages.
- Use all visible text (sidebars, collapsible sections) but drop navigation,
  site footers and "Skip to" links. Mark headings and list items so
  "Research interests" sections survive.

**Why.** Each rule fixes a real miss or false positive:
- Eaton's open-positions page was linked only from his People page.
- Unberath's recruiting note was on his lab's Contact page.
- JHU and UNC directory crawls picked up "please contact Library Services"
  as a contact policy.
- Yatskar's note was in a collapsible section.
- Gevaert's single-file lab page made the whole med school site look like
  "his".

**Consequences.** Crawls are bounded: 8 subpages, 3 extra recruiting pages,
5 subpages per linked site, 2 lab sites.

### D12. Be a polite crawler; never evade blocks (Sep 30 – Oct 2)

**Decision.**
- Respect robots.txt, make at most one request per second per site, and
  send an identifying User-Agent.
- **Never bypass 403s or bot challenges** (e.g. Cloudflare). Unreadable
  pages are listed with links so the user can check them.
- Retry without TLS verification **only** for an incomplete certificate
  chain ("unable to get local issuer certificate"). These are read-only
  fetches of public pages, and the page is flagged.

**Rejected.** Spoofing a browser User-Agent; headless browsers to get past
challenges; scraping Google search results.

### D13. User-submitted evidence (Oct 1)

**Decision.** "Add evidence" accepts a link, optionally with the exact
sentence and what it says.
- If the page can be read, the sentence is verified (D8).
- If the page blocks the app, the sentence is saved as **"not verified"**
  and its confidence is capped at medium.

User evidence is re-checked on every crawl and goes to history if the
sentence disappears.

**Why.** Some sites block automation (e.g. Saria's), and some evidence is
easier for a person to find. Teaching a model per professor isn't practical;
teaching the crawler general rules (D11) is.

### D14. Homepage search: no Google; a pluggable provider (Sep 29 – 30)

**Decision.** Homepage lookup goes through an interface whose real
implementations are Claude's web search tool or the Brave Search API. In
offline mode, the user pastes URLs, or URLs found by research agents (D17)
are imported.

**Why.** Google's Custom Search JSON API is closed to new customers and
shuts down on 2027-01-01, and scraping Google is not allowed. Free research
APIs (OpenAlex, Semantic Scholar, DBLP) don't reliably provide homepages.

---

## Schools and programs

### D15. Resolving school names: catalog → saved schools → OpenAlex (Sep 30)

**Decision.**
- Built-in aliases (UIUC, UNC, TAMU…) come first, then the user's saved
  schools, then OpenAlex institution search.
- An acronym is accepted automatically only if its top match has at least
  5× the publications of the next (UNC → Chapel Hill). Otherwise the user
  picks from suggestions (NU, OSU).
- Domains are validated, and confirming a school merges duplicates and
  remembers the nickname.

**Why.** Users type acronyms ("NU", "UIUC"). Earlier, a full school name
was accepted as a "domain", and duplicate schools were created.

### D16. Hide research fit in offline mode (Sep 30)

**Decision.** The Research fit column, its sort and the dashboard count are
hidden while `LLM_PROVIDER=fake`. They reappear when a real model is
configured.

**Why.** Keyword overlap produced misleading labels, even after weighting
and synonyms. The user didn't want fake results shown.

### D17. Professor discovery by research agents, imported through the normal pipeline (Oct 1–2)

**Decision.** Claude in-session research agents find candidate professors
(with verified homepage URLs) per school. The candidates are added through
the regular bulk-add API, so the crawler re-reads every site and all
recruiting evidence comes from the pages, not from the agents. Each
professor's "why it matches" note is saved and shown in the app.

**Consequences.** 133 professors across 16 schools. The agents' recruiting
quotes are hints; only crawler-verified evidence counts.

### D18. Application tracker (Oct 1)

**Decision.**
- One application per **program**.
- The deadline comes from the program's official page, with its source link
  and exact wording. Dates posted only for last year's cycle are flagged;
  recurring dates with no year ("December 15") are flagged "year not
  stated".
- A default **11-step checklist** gets due dates counted back from the
  deadline (e.g. ask recommenders 6 weeks before). Moving the deadline moves
  the steps that weren't edited by hand.
- A "Do next" list ranks unfinished steps across all applications.
- Each application lists the user's pinned faculty at that school as people
  to name.

**Why.** Many programs admit to the program and ask you to name faculty.
Deadlines cluster on Dec 1 and Dec 15, so step-level urgency matters more
than a list of deadlines.

### D19. Choose programs, not schools, as a portfolio (Oct 2)

**Decision.**
- The unit of choice is a program (e.g. Stanford CS and Stanford Biomedical
  Data Science are different bets).
- Aim for roughly 2 reach + 2 target + 1 likely.
- Prefer programs with at least 3 matching faculty, since admission is to
  the program, not to one advisor.
- The Compare page shows computed facts (matching faculty, how many likely
  advise in that program, recruiting evidence, Fall 2027 statements) next
  to Claude-suggested fit, tier, reasons and gaps. Suggestions are labeled
  and fully editable.
- Decisions (Top 8 / Final 5 / Drop) are the user's.

**Why.** Choosing only by fit would yield five of the most selective
programs. The user's record (MS, two clinical-AI projects, one paper in
review) makes the balance matter.

### D20. CS departments only, except UW (Oct 2, user preference)

**Decision.** Only CS PhD programs are kept, except at the University of
Washington, where the Biomedical & Health Informatics PhD stays alongside
CSE. The 12 non-CS programs are dropped but can be restored.

**Consequences.** UCSF drops out entirely (no CS department), including two
professors with Fall 2027 openings. Stanford CS and BU CS were re-scored as
those schools' only options.

**Update (Oct 7).** The Applications page now follows the same filter.
Programs marked "drop" on Compare, and programs at schools unselected on My
profile, are left out of "Do next", the totals and the main cards. They sit
in a collapsed section, with their checklist progress kept, so restoring one
on Compare or My profile brings it back.

---

## Analysis and UI

### D21. Paper analyses written in-session are imported with verified quotes (Oct 2)

**Decision.** `PUT /papers/{id}/analysis` accepts a summary and connection
points written outside the pipeline (e.g. by Claude in a session). Every
connection must quote the paper and the resume verbatim. The analysis
replaces earlier placeholders and is labeled `analyzed_by`, shown in the UI
as "Analyzed by Claude" vs. "rule-based placeholder".

**Why.** Offline connection points were keyword matches ("both mention
'clinical'"). A real analysis was needed now, without waiting for a Claude
provider integration, and with the same grounding guarantee.

### D22. Professor list: stage groups, pins and plain stage names (Sep 30 – Oct 2)

**Decision.**
- 📌 pin (hover: "Pin" / "Unpin") instead of a "Shortlist" button.
- The list is grouped **Papers analyzed (and later stages) → Pinned →
  Others → Dismissed**, with the chosen sort applied within each group.
- Stage names are plain words (Looking up, New, Pinned, Papers analyzed,
  Email drafted, Contacted, Replied).

**Why.** Requested by the user, so the people being actively worked on stay
at the top.

**Update (Oct 2).**
- **Pinning is a separate `pinned` flag**, independent of the stage, so an
  analyzed or contacted professor can still be unpinned (the user may
  change their mind). Unpinning keeps the stage and moves the professor to
  "Others". Existing pins were carried over by the migration.
- **Within each group, especially close matches rank first.** These are
  professors whose match note says "closest", "direct match/overlap",
  "strongest", "very strong" or "best … match". They're marked ★.
- **The row action is "+ paper"**; the "Open →" link was removed.

---

## Not doing (and why)

| Not doing | Reason |
| --- | --- |
| Scraping Google or Google Scholar | Against their terms; blocked quickly |
| Getting past 403s or Cloudflare challenges | Sites have chosen to block automation (D12) |
| Sending email from the app | The user stays in control; sending from your own inbox is better for deliverability (D1) |
| Crawling entire universities | Scope creep and load on schools; the user picks professors (D2) |
| Letting a model set recruiting status | Status must be reproducible and auditable (D6, D9) |
| Showing keyword-based research fit | Misleading (D16) |

## Open questions

- **Real model provider:** add a Claude API key, or test an 8B Ollama model
  for summaries, connections and emails (D7).
- **Homepage search provider** for adding professors by name alone (D14).
- **Programs not yet researched:** UCSF Computational Precision Health,
  UIUC iSchool PhD, BU Computing & Data Sciences PhD. The first is moot
  under D20 unless UCSF becomes an exception.
- **Harvard and UCLA applications:** still in the tracker though those
  schools are unselected. Delete, withdraw or keep?
