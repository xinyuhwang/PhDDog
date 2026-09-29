# PhDDog — Design Document

**Status:** Draft v0.2 · **Last updated:** 2026-09-29 · **Owner:** Xinyu Wang

> v0.2: Stage ① changed from "scrape faculty listing pages" to **"user types
> professor + school in free-form text; the app finds and reads each
> professor's personal site"**. Recruiting status and contact policy are now
> extracted in the same step.

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

### 1.2 Non-goals (MVP)

- Automatically finding which professors to target. The user supplies names;
  department directories often don't show who is recruiting anyway.
- Scraping Google Scholar or any other site that prohibits automated access.
- Sending email from the app (the user sends from their own inbox).
- User accounts and login. The app has one local user, but the data model
  supports multiple users.
- Admissions data, deadlines or application tracking beyond outreach.

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

---

## 3. Architecture

```text
┌────────────────────┐      REST/JSON      ┌──────────────────────────────┐
│  Next.js frontend  │ ──────────────────► │  FastAPI backend (Python)    │
│  (TypeScript)      │                     │                              │
└────────────────────┘                     │  api/        HTTP routes     │
                                           │  services/   stage logic     │
                                           │  ingest/     fetch + extract │
                                           │  search/     web search adpt │
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
External: Claude API (+ web search tool) · Crossref · arXiv · PubMed/PMC · Unpaywall · Semantic Scholar
```

### 3.1 Technology choices

| Layer | Choice | Rationale |
| --- | --- | --- |
| Frontend | Next.js + TypeScript + Tailwind | Fast to build, popular, easy to deploy later |
| Backend | FastAPI (Python 3.12) | Python has the strongest tools for PDFs, scraping and LLMs |
| DB | Postgres 16 + pgvector | Regular data and embeddings in one database, no migration later |
| ORM / migrations | SQLAlchemy 2 + Alembic | Standard choice |
| Background jobs | Simple DB-backed job table + worker process (MVP); Celery/RQ later | Homepage resolution and paper analysis take too long to run inside a web request |
| Web search | `search/` adapter; default = Claude's server-side web search tool, Brave Search API as an alternative | Used only to find a professor's homepage. Google's Custom Search JSON API is closed to new customers and shuts down 2027-01-01, and scraping Google isn't allowed |
| HTML fetching | `httpx`; Playwright fallback for pages that need JavaScript | Most faculty pages are plain HTML |
| HTML → text | `trafilatura` / `selectolax` | Pulls the main content out of a page |
| PDF → text | PyMuPDF (MVP); GROBID (upgrade) | PyMuPDF is fast; GROBID splits papers into sections |
| LLM | **Claude** (`claude-opus-5-5`) via the `anthropic` Python SDK, behind an `llm/` adapter | Used for parsing, extraction, screening, analysis and writing (§7) |
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
2. **Otherwise search** through the `search/` adapter with targeted queries:
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

1. Crawl the homepage plus up to 8 pages on the same site whose link text
   or path matches `research|publications|people|members|join|prospective|
   openings|students|cv|bio|contact`. Save the raw HTML for each
   (`source_pages`).
2. The LLM extracts, with the source URL for every field:

| Field | Notes |
| --- | --- |
| `title`, `department`(s), `email`, `lab_url` | Directory-style facts |
| `stated_interests`, `bio_summary` | Input to Stage ② screening |
| `recent_publications[]` | Titles and years only. Suggestions for Stage ③; the user still uploads papers |
| `recruiting_status` | `explicitly_recruiting \| recruits_generally \| not_recruiting \| unknown` |
| `recruiting_cycle` | The cycle named in the statement, e.g. "Fall 2026 start". Flagged **stale** if it's earlier than the user's target cycle |
| `contact_policy` | `welcomes_email \| apply_via_program \| do_not_email \| unknown` |
| `recruiting_evidence` | Exact quote + source URL |

Quotes are checked against the saved page text. A field whose quote can't
be found is thrown out, not kept.

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

**UI:** a ranked table with filters (school, department, label,
recruiting status, contact policy) and a shortlist toggle. **Research fit**
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

### 4.5 Professor lifecycle

```text
added → resolved → screened → shortlisted → analyzed → drafted → contacted → (replied | closed)
  └─► needs_review / not_found      └──────► dismissed
```

`Professor.status` is kept up to date from actions in each stage and drives
the dashboard.

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
  user_id, name, aliases[], primary_domain, website, confirmed (bool)

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
  contact_policy (welcomes_email | apply_via_program | do_not_email | unknown),
  recruiting_evidence (text), recruiting_source_url,
  field_sources (jsonb: field → source_page_id),
  user_overrides (jsonb: fields the user edited; never overwritten),
  last_checked_at, status (enum, see §4.5), notes
  UNIQUE (school_id, normalized_name)

homepage_candidates
  professor_id, url, source (user | search | directory_link),
  rank, confidence, reason, chosen (bool)

source_pages
  professor_id, url, final_url (after redirects),
  kind (homepage | subpage | directory),
  raw_html_path, text, fetched_at, fetch_status, extract_status, error

screen_results
  professor_id, profile_version, similarity_score (float),
  label (strong | possible | no), reason (text), model

papers
  professor_id, source_type (pdf | url), source_url, file_path,
  sha256, doi, title, authors[], year, venue,
  full_text, text_status (full | abstract_only | failed),
  summary (jsonb), embedding vector(N)
  UNIQUE (professor_id, doi) / (professor_id, norm_title, year)

connection_points
  professor_id, paper_id, profile_version,
  kind (method_overlap | domain_overlap | future_work_hook),
  paper_evidence (text), user_evidence (text), explanation (text),
  selected (bool)

email_drafts
  professor_id, version (int), subject, body, tone, ask,
  connection_point_ids[], model, edited_by_user (bool)

outreach
  professor_id, email_draft_id, sent_at, to_address,
  subject, body (snapshot), status, follow_up_at, notes

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
| `GET` | `/jobs/{id}` | Background job status |

---

## 7. LLM usage (Claude)

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
  response includes result URLs the app then verifies. This *is* the
  `search/` adapter's default implementation; Brave Search can be added
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
| --- | --- | --- | --- | --- |
| `parse_professor_input` | free-form text | `[{name, school_raw, department_raw, url, issues}]` | low | 1 per paste |
| `normalize_school` | school text | `{name, aliases, primary_domain}` | low | 1 per new school |
| `find_homepage` | name + school + domain, **web search tool** | `[{url, reason}]` candidates | low | 1 per professor (≤3 searches) |
| `verify_homepage` | candidate page text + name + school | `{is_match, confidence, reason}` | low | ≤3 per professor |
| `extract_profile` | homepage + subpage text | profile, publications, recruiting and contact-policy fields with quotes | medium | 1 per professor per refresh |
| `structure_resume` | resume text | structured profile | medium | 1 per resume version |
| `screen_professor` | profile (cached) + interests | `{label, reason}` | low | 1 per professor per screen run (batched) |
| `summarize_paper` | paper text (sections) | structured summary | medium | 1 per paper |
| `find_connections` | summaries + profile (cached) | `[ConnectionPoint]` | high | 1 per analysis |
| `draft_email` | connections + profile + prof | `{subject, body}` | high | 1 per draft |

**Other cost controls:** cache results in the DB by
`(task, prompt_version, model, input_hash)` so re-running a step on
unchanged input costs nothing. Log `usage` for every call to a `llm_calls`
table so real cost per professor can be seen.

**Embeddings:** Claude doesn't provide embeddings, and at this scale (tens
to a few hundred professors) screening can be done by Claude directly. The
MVP therefore **skips embeddings**. The `embedding` columns and pgvector stay
in the schema, unused. If similarity search is wanted later ("professors
like my shortlist"), a local `sentence-transformers` model can fill them
with no new vendor and no data leaving the machine.

--- | --- | --- | --- |
| `parse_professor_input` | free-form text | `[{name, school_raw, department_raw, url, issues}]` | 1 per paste |
| `normalize_school` | school text | `{name, aliases, primary_domain}` | 1 per new school |
| `verify_homepage` | candidate page text + name + school | `{is_match, confidence, reason}` | ≤3 per professor |
| `extract_profile` | homepage + subpage text | profile, publications, recruiting and contact-policy fields with quotes | 1 per professor per refresh |
| `structure_resume` | resume text | structured profile | 1 per resume version |
| `screen_professor` | profile + interests | `{label, reason}` | 1 per professor per screen run |
| `summarize_paper` | paper text (sections) | structured summary | 1 per paper |
| `find_connections` | summaries + profile | `[ConnectionPoint]` | 1 per analysis |
| `draft_email` | connections + profile + prof | `{subject, body}` | 1 per draft |

Cost controls: cache by `(task, prompt_version, input_hash)`, use a smaller
model for extraction and screening, and use a stronger model for connection
finding and emails.

---

## 8. Repository layout

```text
PhDDog/
├── README.md
├── docker-compose.yml
├── .env.example
├── docs/
│   └── DESIGN.md
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── db/            # models, session
│       ├── api/           # routers per resource
│       ├── services/      # resolve, screen, papers, analyze, outreach
│       ├── ingest/        # fetchers, crawler, html/pdf extractors, paper-source handlers
│       ├── search/        # web search provider adapter
│       ├── llm/           # provider adapter, prompts/, schemas
│       ├── storage/       # local / S3 adapter
│       └── worker.py      # job runner
│   └── tests/
├── frontend/
│   ├── package.json
│   └── src/app/
│       ├── profile/
│       ├── add/               # free-form input + parse preview + review queue
│       ├── professors/        # screening board
│       ├── professors/[id]/   # deep-dive + email editor
│       └── outreach/          # tracker
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

| Decision | Options | Current lean |
| --- | --- | --- |
| LLM provider | Claude / OpenAI / local | ✅ **Claude**, `claude-opus-5-5`, effort tuned per task |
| Embedding model | Provider API / local (e.g. sentence-transformers) | ✅ None in MVP; local model later if needed |
| Web search provider | Claude web search tool / Brave Search API / Tavily / Exa | ✅ Claude web search tool |
| Target admission cycle | Setting used for `recruiting_stale` | Fall 2027 |
| Deployment | Local only / hosted | Local only for MVP |
| Paper year window | Fixed 2025–2026 / rolling | Configurable; default = current year + previous year |
