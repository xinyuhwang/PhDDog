# PhDDog — Design Document

**Status:** v0.3 · **Last updated:** 2026-10-02 · **Owner:** Xinyu Wang

> **Why things are the way they are:** see the decision log,
> [DECISIONS.md](DECISIONS.md) (entries D1–D22, referenced below).
>
> v0.3: recruiting evidence with history and computed confidence (§4.1
> Step 5); crawler rules learned from real pages; offline-first providers
> (§7); application tracker (§4.7) and program comparison (§4.6).
> v0.2: professors are added by typing name + school instead of scraping
> faculty listings.

---

## 1. Overview

PhDDog helps a PhD applicant find professors at target schools whose research
matches their interests (HealthTech, Health AI, BioTech, AI × Medicine), dig
into those professors' recent papers to find real points of connection, write
personalized outreach emails, and keep a record of every contact.

The app is a **four-stage funnel**. The user decides who moves forward at
each stage:

```text
① Add & Resolve ──► ② Screen ──────► ③ Deep-dive ──────► ④ Outreach
"Name, School"      match stated      user uploads         draft email,
free-form input →   interests vs.     papers (PDF / link)  log it, track
find personal site  user resume       → connection points  status
→ extract profile
```

### 1.1 Goals (MVP)

- Let the user add professors by typing **name + school** (department is
  optional) in any reasonable format, one or many at a time. For up to 10
  schools, the app finds each professor's personal or lab site and extracts
  title, department, email, research interests, recruiting status and
  contact policy.
- Rank professors against the user's resume and research profile, with a
  short reason for each ranking.
- Let the user add papers for a shortlisted professor as **PDF uploads or
  web links**. Summarize each paper and find concrete connections to the
  user's experience.
- Generate an editable outreach email that cites the connections found.
- Keep an outreach log: who was contacted, when, the final email text,
  status, follow-up date and notes.
- Help choose where to apply: compare programs side by side (§4.6) and track
  each application's deadline and checklist (§4.7).

### 1.2 Non-goals (MVP)

- Automatically finding which professors to target. The user supplies names;
  department directories often don't show who is recruiting anyway.
- Scraping Google Scholar or any other site that prohibits automated access.
- Sending email from the app (the user sends from their own inbox).
- User accounts and login. The app has one local user, but the data model
  supports multiple users.
- Getting past sites that block automated reading (403s, bot challenges).
  The user checks those pages and can add evidence by hand (D12, D13).

### 1.3 Design principles

1. **Nothing is school-specific.** There are no per-school scrapers. Each
   professor is resolved individually from their own site, so adding a new
   school costs nothing.
2. **The user makes the decisions.** The app suggests; the user shortlists,
   picks papers, edits the email and sends it.
3. **Grounded generation.** Every claim in an email must trace back to the
   user's resume or a paper the user supplied. No invented experience.
4. **Keep raw inputs.** Store raw HTML, PDFs and extracted text so any step
   can be re-run without fetching again.
5. **Swappable integrations.** The LLM provider, embedding model, file
   storage and paper sources each sit behind a small interface.

---

## 2. User flow

1. **Set up profile.** Upload a resume (PDF). Optionally add a free-text
   research statement and keywords. The app extracts a structured profile.
2. **Add professors.** Type or paste one or more entries into a single text
   box, for example `Jacob Gardner (UPenn CIS)` or `Mark Yatskar, UPenn`.
   The app shows a preview of how it read each entry before running.
3. **Review resolution.** The app finds each professor's personal site and
   extracts their details. Entries that didn't match clearly are shown for
   the user to confirm: pick the right candidate or paste the URL.
4. **Screen.** The app ranks each professor *Strong / Possible / No* with a
   score and a one-line reason. The user shortlists.
5. **Deep-dive.** For a shortlisted professor, the user uploads PDFs or
   pastes paper links (ideally 2025–2026 papers). The app summarizes each
   paper and proposes connection points.
6. **Draft email.** The user picks connection points and a tone. The app
   drafts a subject and body. The user edits; every version is saved.
7. **Log outreach.** The user sends the email from their own inbox and
   clicks "Mark as sent". Status, follow-up date and notes are tracked from
   then on.
8. **Choose programs.** On **Compare**, the user narrows target programs to
   a Top 8 and a Final 5 using computed faculty and recruiting facts plus
   suggested fit and tier (§4.6).
9. **Track applications.** On **Applications**, each program has its
   deadline, apply link, requirements and an 11-step checklist; "Do next"
   lists the most urgent steps (§4.7).

---

## 3. Architecture

```text
┌────────────────────┐      REST/JSON      ┌──────────────────────────────┐
│  Next.js frontend  │ ──────────────────► │  FastAPI backend (Python)    │
│  (TypeScript)      │                     │                              │
└────────────────────┘                     │  api/        HTTP routes     │
                                           │  services/   stage logic     │
                                           │  ingest/     fetch + extract │
                                           │  llm/        provider adapter│
                                           │  storage/    file adapter    │
                                           │  worker      background jobs │
                                           └──────┬──────────────┬────────┘
                                                  │              │
                                   ┌──────────────▼───┐   ┌──────▼─────────┐
                                   │ Postgres 16 +    │   │ File storage   │
                                   │ pgvector         │   │ ./data (local) │
                                   └──────────────────┘   │ → S3 later     │
                                                          └────────────────┘
External: OpenAlex (schools) · Crossref · arXiv · PubMed/PMC · Unpaywall · optional: Ollama (local), Claude API
```

### 3.1 Technology choices

| Layer | Choice | Rationale |
| --- | --- | --- |
| Frontend | Next.js + TypeScript + Tailwind | Fast to build, popular, easy to deploy later |
| Backend | FastAPI (Python 3.12) | Python has the strongest tools for PDFs, scraping and LLMs |
| DB | Postgres 16 + pgvector | Regular data and embeddings in one database, no migration later |
| ORM / migrations | SQLAlchemy 2 + Alembic | Standard choice |
| Background jobs | Simple DB-backed job table + worker process (MVP); Celery/RQ later | Homepage resolution and paper analysis take too long to run inside a web request |
| Web search | Behind the LLM adapter's `find_homepage`; planned: Claude's web search tool or Brave Search. Offline: pasted URLs or URLs from research agents (D14, D17) | Used only to find a professor's homepage. Google's Custom Search JSON API is closed to new customers and shuts down 2027-01-01, and scraping Google isn't allowed |
| HTML fetching | `httpx`; Playwright fallback for pages that need JavaScript | Most faculty pages are plain HTML |
| HTML → text | `trafilatura` / `selectolax` | Pulls the main content out of a page |
| PDF → text | PyMuPDF (MVP); GROBID (upgrade) | PyMuPDF is fast; GROBID splits papers into sections |
| LLM | `llm/` adapter with three providers: `fake` (rule-based, **default**), `ollama` (local extraction), `claude` (planned) | §7; D5–D7 |
| Embeddings | None in MVP; local `sentence-transformers` later (§7) | pgvector columns reserved |
| Local dev | Docker Compose | One command runs everything |

---

## 4. Stage details

### 4.1 Stage ① Add & Resolve

**Input:** free-form text in a single input box, with one or more entries.
Each entry needs a **professor name** and a **school**. Department and URL
are optional. All of these are valid:

```text
Jacob Gardner (UPenn CIS)
Mark Yatskar, UPenn
Eric Eaton - University of Pennsylvania, Computer Science
Pranam Chatterjee UPenn Bioengineering https://www.chatterjeelab.com/
Li Shen, Penn Medicine; Christos Davatzikos, Penn Radiology
```

Entries are split by newlines or `;`. The order of fields and the separators
between them don't matter.

#### Step 1: Parse (synchronous, preview before running)

The LLM reads the text and returns one record per entry:

```json
{ "name": "Jacob Gardner", "school_raw": "UPenn", "department_raw": "CIS",
  "url": null, "issues": [] }
```

- An entry with no school, or no recognizable name, gets an issue such as
  `missing_school`. It is highlighted in the preview, and the user can fix
  it in place.
- **School shorthand:** a school the user has used before carries over to
  the next line *only if* the user sets it with a header line such as
  `UPenn:`. Otherwise a line without a school is flagged, not guessed.
- Duplicates (the same name and school as an existing professor) are flagged
  and not added again.

#### Step 2: Normalize the school

- Look up `school_raw` against `schools.name` and `schools.aliases`.
  "UPenn", "Penn" and "University of Pennsylvania" all map to one school
  with `primary_domain = upenn.edu`.
- For a school the app hasn't seen before, the LLM proposes the official
  name, aliases and primary domain. The user confirms it once, and it is
  saved for next time.
- The department is kept as written for now and replaced with what the
  professor's own site says after Step 4.

#### Step 3: Find the homepage (background job)

1. **URL given in the entry:** use it directly and skip to verification.
2. **Otherwise search** (planned provider: Claude web search or Brave, D14; offline mode skips this step) with targeted queries:
   - `"{name}" {school} homepage`
   - `"{name}" {department} site:{primary_domain}`
   - `"{name}" {school} lab`
3. **Rank candidates:**
   - Personal and lab pages on the school's domain, and personal sites
     (`github.io`, `sites.google.com`, a personal domain) that mention the
     school, rank highest.
   - Directory profile pages on the school's domain rank next. They are
     also used to find a link to the personal site.
   - News articles, LinkedIn, Scholar, RateMyProfessors and similar sites
     are dropped.
4. **Verify:** fetch the top candidates, following redirects (faculty sites
   often move). The LLM confirms that the page belongs to *this* person *at
   this* school and returns a confidence score.
5. **Outcome:**
   - `resolved`: one confident match.
   - `needs_review`: several plausible matches (for example, two people
     with the same name) or low confidence. The UI shows the candidates, and
     the user picks one or pastes a URL.
   - `not_found`: the user pastes a URL or enters details by hand.

#### Step 4: Read the site and extract details

1. **Crawl** (D11). Save the raw HTML of every page (`source_pages`).
   - The homepage plus up to 8 subpages **within the profile's path prefix**
     (so `/faculty/jane-doe/` doesn't wander into department pages).
     Recruiting-style links (open positions, join, prospective, contact…)
     come first.
   - **One extra hop** (up to 3 pages) for recruiting-style links that
     appear only on a subpage.
   - **"Website / Homepage / Lab" links** off a directory profile, each
     explored like a homepage (up to 5 subpages).
   - **Lab sites** linked from the personal site (up to 2), labeled `lab`.
   - **Pages the user submitted** as evidence, always re-read.
   - Page text keeps everything visible (sidebars, collapsible sections),
     drops navigation, site footers and "Skip to" links, and marks headings
     (`## `) and list items (`- `).
   - Pages that fail are kept and listed; 403s and bot challenges are never
     bypassed. Incomplete TLS chains are retried unverified and flagged
     (D12).
2. Extraction (offline rules or a model) returns, with the source URL for
   every field:

| Field | Notes |
| --- | --- |
| `title`, `department`(s), `email`, `lab_url` | Directory-style facts |
| `stated_interests`, `bio_summary` | Input to Stage ② screening |
| `recent_publications[]` | Titles and years only. Suggestions for Stage ③; the user still uploads papers |
| `claims[]` | Every recruiting or contact-policy statement: kind, claim, cycle named, **exact quote**, source URL. Interpretation rules: D10 |

Quotes are checked against the saved page text. A field whose quote can't
be found is thrown out, not kept.

#### Step 5: Evidence and status (deterministic code, no model)

Extraction returns every recruiting and contact-policy statement it finds as
a **claim** (claim, cycle, exact quote, source URL). Each is stored as an
`evidence` row with its source type (`personal | lab | faculty_profile |
department | admissions`, classified from the URL), the page's own "last
updated" date when known, and first-seen / last-seen times. A statement that
disappears from a page on a later check is kept, marked `gone_at`, and no
longer counts.

The professor's status and confidence are computed from current evidence:

- **Pick:** a statement naming the target cycle (or later) beats an undated
  one, which beats one naming an earlier cycle; then the more personal
  source; then explicit statements over "every year" ones.
- **Confidence:** *high* = explicit statement for the target cycle on their
  own page; *medium* = their own page, but undated or a general statement;
  *low* = an earlier cycle, or not from their own page.
- **Contact policy:** the most restrictive statement from their own pages.

The UI never turns missing evidence into "no": it shows **"No recruiting
evidence found"** or **"Only older evidence"** with the last-checked date and
a re-check button, and flags checks older than `RECHECK_AFTER_DAYS` (60).
Pages the crawler couldn't read (e.g. 403) are listed so the user can check
them by hand.

**Refresh:** the user can re-run Step 4 on demand. It is worth re-checking
in October–November, when many professors update their recruiting notes.

**Politeness:** 1 request/sec per domain, respect `robots.txt`, use a
descriptive User-Agent, and cache pages for 7 days.

**Failure handling:** every professor shows its `resolve_status`, and every
`source_page` records its fetch/extract status. The user can retry, switch
to Playwright, paste a different URL, or edit any field by hand. User edits
are never overwritten by a refresh.

### 4.2 Stage ② Screen

**Input:** `UserProfile` + `Professor.stated_interests`.

**Pipeline**
1. *(Optional, later)* Embed the user profile and each professor's stated
   interests. The MVP skips embeddings (§7).
2. *(Optional, later)* Compute cosine similarity for a `similarity_score`.
3. The LLM classifies each professor as `strong | possible | no`, with a
   one-sentence reason. Volume is small (tens to a few hundred professors),
   so all of them are classified.
4. Store the result in `ScreenResult`, versioned by `profile_version` so a
   changed resume triggers a re-screen.

**Offline mode:** research fit is hidden, because keyword overlap was
misleading (D16). It reappears with a real model.

**UI:** a table grouped **Papers analyzed → Pinned → Others → Dismissed**
(D22; the first two require `professors.pinned`), with ★ strong matches
first in each group, filters (school, search), a 📌 pin toggle on every row
and a "+ paper" shortcut. **Research fit**
(from screening) and **recruiting status** (from §4.1 Step 4) are separate
columns, so the user can sort by either.

### 4.3 Stage ③ Deep-dive (paper intake + analysis)

**Input:** papers that the user supplies for one professor. The
`recent_publications` list found in §4.1 is shown as suggestions, and the
user can paste any of them as a link.

**Intake: PDF upload**
1. Save the file to storage at `papers/{professor_id}/{sha256}.pdf`.
2. PyMuPDF extracts the full text. Metadata comes from PDF info plus the
   first-page text.
3. If a DOI is found, fill in the metadata from Crossref.

**Intake: web link.** Handlers are tried in order:

| URL pattern | Handler |
| --- | --- |
| `arxiv.org` | arXiv API → metadata + PDF |
| `biorxiv.org` / `medrxiv.org` | bioRxiv API → metadata + PDF |
| `pubmed.ncbi.nlm.nih.gov`, PMC | NCBI E-utilities → metadata; PMC full text if open access |
| DOI (`doi.org/…` or bare DOI) | Crossref → metadata; Unpaywall → open-access PDF |
| Any other URL | Fetch + `trafilatura` article extraction |
| Paywalled / blocked | Keep the abstract if available, mark `text_status = abstract_only`, ask for the PDF |

**De-duplication:** by DOI; otherwise by normalized title + year.

**Year check:** show a warning (not a filter) if `year` is outside the
configured window (default: current year and the year before).

**Analysis**
1. **Per-paper structured summary** (LLM, with long papers split into
   sections):
   ```json
   {
     "problem": "...", "methods": ["..."], "data_modalities": ["..."],
     "application_setting": "...", "key_findings": ["..."],
     "limitations": ["..."], "future_work": ["..."]
   }
   ```
2. **Connection points** (LLM): compare the summaries with the user's
   structured profile. Each connection point is one of:
   - `method_overlap`: the professor uses X; the user has built or used X.
   - `domain_overlap`: same disease area, data modality or clinical setting.
   - `future_work_hook`: a stated limitation or next step that the user's
     experience addresses.

   Each connection point must cite the specific paper field *and* the
   specific resume item it relies on. The validator rejects any whose
   evidence cannot be found.

### 4.4 Stage ④ Outreach

**Contact-policy guard:** if `contact_policy = do_not_email` or
`apply_via_program`, the draft screen shows the professor's quote and source
before generating. The user can go ahead (for example, asking about a
specific paper or an RA role rather than admissions), but the app never hides
the warning.

**Email generation**
- Inputs: the selected connection points, the professor's details, the
  user's profile, the tone (`formal | warm`), the ask (`PhD | RA | both`).
- Constraints: 150–200 words. Cite at least one paper by its exact title.
  Mention only facts found in the resume. End with a specific,
  low-pressure ask. Add a subject line.
- Each generation or edit is saved as a new `EmailDraft` version.

**Outreach log**
- "Mark as sent" creates an `Outreach` record with `sent_at`, the recipient,
  and the final subject and body (a snapshot of the draft).
- Status: `sent → replied | no_response → follow_up_sent → meeting | declined`.
- `follow_up_at` defaults to sent + 14 days. The dashboard shows follow-ups
  that are due.

**Analyses written outside the pipeline** (e.g. by Claude in a session) are
imported with `PUT /papers/{id}/analysis`. Every connection point must quote
the paper and the resume verbatim, and is labeled with `analyzed_by` (D21).

### 4.5 Professor lifecycle

```text
added → resolved → screened → shortlisted → analyzed → drafted → contacted → (replied | closed)
  └─► needs_review / not_found      └──────► dismissed
```

`Professor.status` is kept up to date from actions in each stage and drives
the dashboard. The UI shows it as plain stage names: Looking up, New,
Pinned, Papers analyzed, Email drafted, Contacted, Replied, Closed,
Dismissed.

### 4.6 Choosing programs (Compare page)

One row per application at a **target school** (D19):

- **Computed:**
  - matched faculty at the school, and how many likely advise through
    *this* program (a heuristic on department names),
  - how many of those have current recruiting evidence, and how many name
    the target cycle,
  - program type and deadline.
- **Assessment:** fit 1–5, tier (reach / target / likely), "why apply", and
  gaps & risks. Pre-filled as `assessment_by = claude` and shown as
  "suggested"; any edit makes it `user`.
- **Decision:** undecided / top8 / final5 / drop, with counters for 8 and 5
  and the reach/target/likely mix. Decisions are the user's.

### 4.7 Application tracker (Applications page)

- One application per program, with:
  - the deadline, its exact wording and source URL,
  - a cycle flag: `fall2027`, `previous` (only last year's date posted), or
    `unknown` (year not stated),
  - the apply URL and requirements (GRE, letters, fee, English test,
    faculty naming).
- Creating an application adds an **11-step checklist**. Each step's due
  date is counted back from the deadline (e.g. ask recommenders 42 days
  before; submit on the deadline). Moving the deadline moves the default
  steps that weren't edited by hand.
- **Do next:** unfinished steps across active applications, sorted by due
  date.
- Each card lists **faculty to name**: the user's pinned professors at that
  school, with their recruiting and contact status.
- Schools are selected on My profile (`schools.is_target`).

---

## 5. Data model

All tables have `id` (UUID), `created_at` and `updated_at`. `user_id` is
included from the start so multiple users can be added without a data
migration.

```text
users
  id, email, name

user_profiles
  user_id → users, version (int), resume_file_path, resume_text,
  research_statement, keywords[], structured_profile (jsonb),
  embedding vector(N), is_active

schools
  user_id, name, aliases[], primary_domain, website, confirmed (bool),
  suggestions (jsonb: OpenAlex candidates when unrecognized), is_target (bool)

professors
  school_id, name, input_raw (text the user typed),
  department_raw, department, title, email,
  homepage_url, lab_url, scholar_url (reference only, never fetched),
  resolve_status (pending | resolved | needs_review | not_found),
  resolve_confidence (float),
  stated_interests (text), bio_summary, embedding vector(N),
  recent_publications (jsonb: [{title, year, url?}]),
  recruiting_status (explicitly_recruiting | recruits_generally |
                     not_recruiting | unknown),
  recruiting_cycle (text), recruiting_stale (bool),
  recruiting_confidence (high | medium | low; cached from evidence),
  contact_policy (welcomes_email | apply_via_program | do_not_email | unknown),
  recruiting_evidence (text), recruiting_source_url,
  field_sources (jsonb: field → source_page_id),
  user_overrides (jsonb: fields the user edited; never overwritten),
  last_checked_at, status (enum, see §4.5), pinned (bool, independent of status), notes
  UNIQUE (school_id, normalized_name)

evidence
  professor_id, kind (recruiting | contact_policy), claim, cycle,
  quote, quote_hash, source_url, source_type, page_updated_at,
  first_seen_at, last_seen_at, gone_at, extractor (fake | ollama:… | user),
  verified (false only for user sentences from unreadable pages)
  UNIQUE (professor_id, kind, source_url, quote_hash)

homepage_candidates
  professor_id, url, source (user | search | directory_link),
  rank, confidence, reason, chosen (bool)

source_pages
  professor_id, url, final_url (after redirects),
  kind (homepage | subpage | linked_site | lab_site | user_submitted),
  raw_html_path, text, page_updated_at, fetched_at, fetch_status, error

screen_results
  professor_id, profile_version, similarity_score (float),
  label (strong | possible | no), reason (text), model

papers
  professor_id, source_type (pdf | url), source_url, file_path,
  sha256, doi, title, authors[], year, venue,
  full_text, text_status (full | abstract_only | failed),
  summary (jsonb), summary_by, embedding vector(N)
  UNIQUE (professor_id, doi) / (professor_id, norm_title, year)

connection_points
  professor_id, paper_id, profile_version,
  kind (method_overlap | domain_overlap | future_work_hook),
  paper_evidence (text), user_evidence (text), explanation (text),
  selected (bool), analyzed_by

email_drafts
  professor_id, version (int), subject, body, tone, ask,
  connection_point_ids[], model, edited_by_user (bool)

outreach
  professor_id, email_draft_id, sent_at, to_address,
  subject, body (snapshot), status, follow_up_at, notes

applications
  user_id, school_id, program, deadline, deadline_text, deadline_cycle,
  deadline_source_url, apply_url, requirements (jsonb),
  status (planning | in_progress | submitted | interview | admitted |
          waitlisted | rejected | withdrawn), notes,
  fit_score (1–5), tier (reach | target | likely), reason, gaps,
  decision (undecided | top8 | final5 | drop), assessment_by (claude | user)

application_steps
  application_id, label, position, done, done_at, due_date

jobs
  kind, payload (jsonb), status (queued | running | done | failed),
  attempts, error, started_at, finished_at
```

---

## 6. API (v1)

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/profile/resume` | Upload a resume; creates a new profile version |
| `GET/PUT` | `/profile` | View or edit the research statement and keywords |
| `POST` | `/professors/parse` | Free-form text → parsed entries + issues (preview; nothing saved) |
| `POST` | `/professors/bulk` | Save the confirmed entries; queues resolve jobs |
| `GET` | `/professors/{id}/candidates` | Homepage candidates for `needs_review` |
| `POST` | `/professors/{id}/homepage` | Choose a candidate or set a URL; queues extraction |
| `POST` | `/professors/{id}/refresh` | Re-crawl and re-extract (keeps user edits) |
| `GET/POST/PATCH` | `/schools` | List schools, confirm new ones, edit aliases |
| `GET` | `/professors?school=&label=&status=` | Screening board |
| `PATCH` | `/professors/{id}` | Edit fields, shortlist or dismiss |
| `POST` | `/screen` | Re-run screening for the active profile |
| `POST` | `/professors/{id}/papers` | Upload a PDF (multipart) or submit `{url}` |
| `GET` | `/professors/{id}/papers` | Papers + summaries |
| `POST` | `/professors/{id}/analyze` | Generate connection points |
| `POST` | `/professors/{id}/drafts` | Generate an email draft |
| `PUT` | `/drafts/{id}` | Save a user edit (new version) |
| `POST` | `/professors/{id}/outreach` | Mark as sent (snapshots the draft) |
| `PATCH` | `/outreach/{id}` | Update status, follow-up date, notes |
| `GET` | `/outreach?due=true` | Outreach tracker / follow-ups due |
| `POST` | `/professors/{id}/evidence` | Add evidence: a URL, optionally with the exact sentence (verified; unverified if the page blocks the app) |
| `DELETE` | `/professors/evidence/{id}` | Remove evidence the user added |
| `PUT` | `/papers/{id}/analysis` | Import a summary + connection points; quotes verified |
| `POST` | `/schools` · `PATCH` `/schools/{id}/target` · `POST` `/schools/{id}/confirm` | Add a school by name, select it as a target, confirm/merge an unrecognized one |
| `GET/POST/PATCH/DELETE` | `/applications` | Application tracker; PATCH also sets assessment fields |
| `POST` `/applications/{id}/steps` · `PATCH/DELETE` `/application-steps/{id}` | | Checklist steps |
| `GET` | `/applications/todo` | "Do next" across applications |
| `GET` | `/compare` | Compare-page rows for target schools |
| `GET` | `/jobs`, `/jobs/{id}` | Background job status |

---

## 7. LLM usage

**Current state (D5–D7):**

| Provider | Status | Used for |
| --- | --- | --- |
| `fake` | **Default.** Rule-based, offline, deterministic | All tasks. Recruiting/contact extraction and interests are reliable; generated text is marked `[FAKE]` |
| `ollama` | Implemented; evaluated with `llama3.2` 3B and **not adopted** for extraction (12 of 25 claims invented) | `extract_profile` only; everything else falls back to the rules |
| `claude` | Planned (needs `ANTHROPIC_API_KEY`); not yet implemented | The plan below |
| Claude in-session | Used now via research agents and `PUT /papers/{id}/analysis` | Professor discovery (D17), paper analysis (D21) |

The rest of this section is the plan for the `claude` provider.

**Provider:** Anthropic Claude, called through the official `anthropic`
Python SDK. The API key lives in `.env` as `ANTHROPIC_API_KEY`. The rest of
the app talks only to `llm/`, so another provider could be added later
without changes elsewhere.

**Model:** `claude-opus-5-5` for every task in the MVP. Cost and depth are
tuned per task with the **effort** setting instead of by switching models.
The model is configurable per task, so a cheaper model (e.g.
`claude-sonnet-5-5`) can be tried on bulk tasks later if the bill calls for
it. That is a measured decision, not a default.

**How the calls are made**
- **Structured output:** `client.messages.parse()` with a Pydantic model for
  each task. The response is validated against the schema, with no
  hand-written JSON parsing.
- **Thinking:** adaptive (the default; it can't be turned off on Opus 5.5).
  Effort is **always set explicitly**, because Opus 5.5 defaults to `medium`.
- **Web search:** the server-side `web_search_20260209` tool, used only in
  `find_homepage`. Claude runs the searches on Anthropic's side, and the
  response includes result URLs the app then verifies. This is the
  default homepage-search implementation; Brave Search can be added
  behind the same interface.
- **Refusals:** check `stop_reason` before reading content. Server-side
  fallback is enabled (`fallbacks: "default"` with its beta header). This
  matters for PhDDog in particular: safety classifiers include a `bio`
  category, and a BioTech or medical paper could occasionally be declined by
  mistake. The fallback retries it without the app having to handle it.
- **Streaming** for long inputs and outputs (paper summaries), using
  `.get_final_message()`.
- **Batches API (50% cheaper, runs asynchronously):** used for re-screening
  every professor after a resume change, since nothing is waiting on it.
- **Prompt caching:** the system prompt and the user's structured profile go
  first in every screening and connection call and are cached, so only the
  professor- or paper-specific part is billed at the full rate. Check
  `usage.cache_read_input_tokens` to confirm hits.

| Task | Input | Output | Effort | Volume |
| --- | 
---

## 8. Repository layout

```text
PhDDog/
├── README.md
├── docker-compose.yml
├── .env.example
├── docs/
│   ├── DESIGN.md
│   └── DECISIONS.md       # decision log
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── db/            # models, session
│       ├── api/           # routers per resource
│       ├── services/      # professors (resolve/crawl), evidence, schools, screen, papers, outreach, applications, jobs
│       ├── ingest/        # fetch, html (text + link rules), pdf, paper sources, openalex
│       ├── llm/           # adapter: fake (rules), ollama, claude (planned); schemas
│       ├── storage/       # local / S3 adapter
│       └── worker.py      # job runner
│   └── tests/
├── frontend/
│   ├── package.json
│   └── src/app/
│       ├── profile/
│       ├── add/               # free-form input + parse preview + review queue
│       ├── professors/        # screening board
│       ├── professors/[id]/   # recruiting evidence, papers, connections, email editor
│       ├── outreach/          # outreach log
│       ├── compare/           # choose programs
│       └── applications/      # deadlines + checklists
└── data/                  # gitignored: raw html, pdfs, resumes
```

---

## 9. Milestones

| # | Milestone | Done when |
| --- | --- | --- |
| M0 | Scaffold | `docker compose up` runs the API, frontend and DB; migrations run |
| M1 | Profile | Resume upload → structured profile visible and editable |
| M2 | Add & Resolve + Screen | Paste ~10 names across 2 schools → ≥80% resolve without help; the rest go to the review queue; ranked list with fit and recruiting columns |
| M3 | Paper intake | PDF + arXiv/PubMed/DOI/generic links → stored text + summary |
| M4 | Connections | Connection points with cited evidence for a professor |
| M5 | Email + Outreach log | Draft → edit → mark sent → tracker with follow-ups |
| M6 | Scale to 10 schools | Resolution holds up across all target schools; refresh keeps user edits |

The app is usable for real outreach after **M5**.

---

## 10. Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Wrong person resolved (common names, moved faculty) | Match on school domain + LLM check + confidence threshold → `needs_review`; the user can always paste a URL |
| Search provider cost or limits | Search is used only to find homepages (≈3 queries per professor); results cached; a pasted URL skips search |
| Personal sites vary widely or need JavaScript | LLM extraction, Playwright fallback, manual edit in the UI |
| Recruiting notes are stale or misread | Store the exact quote + URL + cycle; `recruiting_stale` flag; quotes checked against page text |
| Profile interests are outdated or vague | Screening is only a first pass; the deep-dive on papers is the real signal |
| Paywalled paper links | Unpaywall / PMC lookup; `abstract_only` status; ask for a PDF |
| Messy PDF text (columns, headers) | PyMuPDF with block ordering; GROBID upgrade path |
| LLM invents facts in emails | Evidence-linked connection points; validator; the user always edits before sending |
| LLM cost | Per-task effort, prompt caching, the Batches API for re-screening, DB result cache, and a small total volume (≤10 schools) |
| A biotech or medical paper is declined by a safety classifier by mistake | Server-side refusal fallback; check `stop_reason`; show the paper as "analysis failed, retry" rather than failing silently |
| Hitting school sites too often | Rate limits, robots.txt, 7-day cache, ≤9 pages per professor |
| Personal data (resume, emails) | Local-only by default; `data/` is gitignored; no third-party storage in MVP |

---

## 11. Future work

- Gmail/Outlook integration: send from the app, find replies automatically,
  follow-up reminders.
- Automatic paper suggestions (OpenAlex / Semantic Scholar) for the user to
  confirm.
- More "likely taking students" signals: career stage, new-hire
  announcements, students near graduation (from lab People pages), and
  active grants (NIH RePORTER, NSF Award Search).
- Optional bulk import from a department directory URL, for schools where
  one exists.
- Multiple users with auth; hosted deployment.
- "Professors similar to your shortlist" across schools.
- Scheduled refresh of recruiting status during application season.

---

## 12. Open decisions

Settled decisions and their reasons are in [DECISIONS.md](DECISIONS.md).
Still open:

| Decision | Options | Current lean |
| --- | --- | --- |
| Real model provider | Claude API key / 8B local model (Ollama) | Test on summaries, connections and emails, not extraction (D7) |
| Homepage search | Claude web search / Brave Search | Needed only to add professors by name alone (D14) |
| Unresearched programs | UCSF Computational Precision Health, UIUC iSchool, BU Computing & Data Sciences | Research if they could make the shortlist |
| Unselected schools' applications | Delete / mark withdrawn / keep (Harvard, UCLA) | Ask the user |
| Target admission cycle | Setting used for staleness | Fall 2027 |
| Deployment | Local only / hosted | Local only |
