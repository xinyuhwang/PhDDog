# PhDDog 🐶🎓

**Find the right PhD advisors, read their recent work, and reach out with emails that show you've actually read it.**

PhDDog is a full-stack tool for PhD applicants in **HealthTech, Health AI,
BioTech and AI × Medicine**. You give it faculty pages from your target
schools and your resume. It finds professors whose research matches yours,
analyzes the papers you choose, drafts outreach emails based on concrete
connections, and keeps a record of everyone you've contacted.

> **Status:** MVP scaffold. All four stages work end to end in offline mode; the Claude
> integration is next. See [docs/DESIGN.md](docs/DESIGN.md) for the design and
> [docs/DECISIONS.md](docs/DECISIONS.md) for why it works the way it does.

---

## How it works

```text
① Add & Resolve ──► ② Screen ──────► ③ Deep-dive ──────► ④ Outreach
"Name, School" →    match stated      you upload papers    draft email,
app finds their     interests vs.     (PDF or link) →      log it, track
personal site       your resume       connection points    follow-ups
```

1. **Add & Resolve:** type professors into one box, in whatever format is
   convenient, e.g. `Jacob Gardner (UPenn CIS)` or `Mark Yatskar, UPenn`.
   Each entry needs a name and a school. PhDDog finds each professor's
   personal or lab site and extracts their title, email, research
   interests, **recruiting status** and **contact policy** (for example,
   "apply through the program, don't email"), with a quote and link as
   evidence. Unclear matches go to a review queue.
2. **Screen:** your resume and research statement are compared with each
   professor's interests. Each professor is ranked *Strong / Possible / No*
   with a one-line reason. You shortlist.
3. **Deep-dive:** for a shortlisted professor, upload their recent papers as
   PDFs or paste links (arXiv, bioRxiv/medRxiv, PubMed, DOI or any article
   page). PhDDog summarizes each paper and finds **connection points**:
   method overlap, domain overlap, and gaps in their future work that match
   your experience.
4. **Outreach:** generate an editable email (150–200 words) based on those
   connections, send it from your own inbox, and log it. Track status
   (sent → replied → meeting) and follow-up dates.

## Features

Built, and runs fully offline. Items marked *(offline: rule-based)* use
placeholder logic until a Claude API key is configured.

- [x] Resume upload → research profile (versioned)
- [x] Free-form "Name, School" input with a parse preview; school-name
      resolution (catalog → saved schools → OpenAlex)
- [x] Homepage lookup, polite crawling and profile extraction
- [x] Recruiting status and contact policy from evidence with quotes and
      history. Cycles are recognized, including academic years like
      "2027-28"; undated statements are labelled "undated".
- [x] User-submitted evidence (a URL, optionally with the exact sentence)
- [ ] Interest-based screening *(offline: rule-based; research fit hidden)*
- [x] Paper intake from PDFs and web links
- [x] Paper summaries and connection points *(offline: rule-based; analyses
      written in a Claude session can be imported with verified quotes)*
- [x] Email drafts with saved versions *(offline: template)*; outreach log
      with follow-ups
- [x] Outreach to-do tasks (steps, links, notes) per professor
- [x] Application tracker: deadlines, an 11-step checklist, "Do next"
- [x] Compare page: fit, tier and decision for each program
- [x] Publishing page: ranked conference and journal targets with deadlines
- [x] Funding outlook per school (⚠ concern, ⓘ minor, ✓ funded) on My
      profile
- [x] Admission chances per selected program, with evidence for each reason
      *(needs Claude; session-written evaluations can be imported)*

## Tech stack

| Layer | Tech |
| --- | --- |
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | FastAPI (Python 3.12), SQLAlchemy, Alembic |
| Database | PostgreSQL 16 + pgvector |
| Parsing | httpx, Playwright (fallback), trafilatura, PyMuPDF |
| Web search | Planned (Claude web search or Brave), only to find homepages; offline you paste URLs |
| Paper metadata | Crossref, arXiv, PubMed/PMC, Unpaywall |
| LLM | Pluggable: offline rules (default), Ollama (local), Claude (planned) |
| Dev environment | Docker Compose |

## Project structure (planned)

```text
PhDDog/
├── backend/        # FastAPI app, workers, ingestion, LLM adapter
├── frontend/       # Next.js app
├── docs/           # Design docs
├── data/           # Local files: resumes, PDFs, raw HTML (gitignored)
└── docker-compose.yml
```

## Getting started

Requires Docker. No API key is needed: by default the app runs in **offline
mode** (`LLM_PROVIDER=fake`), where rule-based stand-ins replace Claude.
Fetching sites, reading PDFs, paper lookups, the database and the UI are all
real; generated text (summaries, connections, emails) is marked `[FAKE]`.

```bash
git clone https://github.com/xinyuhwang/PhDDog.git
cd PhDDog
cp .env.example .env
docker compose up -d --build
```

- App: <http://localhost:3000> (set `FRONTEND_PORT` in `.env` if 3000 is taken)
- API docs: <http://localhost:8000/docs> (set `API_PORT` in `.env` if 8000 is taken; the frontend follows it)
- The background worker must be running (`docker compose ps`). If it exited
  after a database restart, run `docker compose up -d worker`.

In offline mode, homepages can't be searched for, so include the URL in the
entry (`Name, School https://...`) or paste it when the app asks. A few
professors are pre-filled in `backend/app/llm/fake_homepages.json` for testing.

### Backend tests

```bash
docker compose up -d db
cd backend && uv run pytest
```

### Running without Docker for the app

Keep Postgres in Docker (`docker compose up -d db`), then in separate terminals:

```bash
cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload
cd backend && uv run python -m app.worker
cd frontend && npm install && npm run dev
```

## Roadmap

| Milestone | Scope |
| --- | --- |
| M0 | Project scaffold (Docker, DB, API, frontend) |
| M1 | Resume upload + structured profile |
| M2 | Add & Resolve professors + screening |
| M3 | Paper intake (PDF + links) + summaries |
| M4 | Connection points |
| M5 | Email drafts + outreach log (**usable end-to-end**) |
| M6 | Scale to all target schools |

Later: Gmail integration, automatic paper suggestions, NIH grant signals,
multi-user hosting.

## Privacy

PhDDog runs locally by default. Your resume, papers and emails stay in the
local `data/` folder and your local database. Text is sent only to the Claude API
(Anthropic).

When fetching faculty pages, PhDDog follows `robots.txt`, sends at most one
request per second to each site, and caches pages. It never scrapes Google
Scholar.

## License

[Apache 2.0](LICENSE)
