# PhDDog 🐶🎓

**Find the right PhD advisors, read their recent work, and reach out with emails that show you've actually read it.**

PhDDog is a full-stack tool for PhD applicants in **HealthTech, Health AI,
BioTech and AI × Medicine**. You give it faculty pages from your target
schools and your resume. It finds professors whose research matches yours,
analyzes the papers you choose, drafts outreach emails based on concrete
connections, and keeps a record of everyone you've contacted.

> **Status:** early design stage. See [docs/DESIGN.md](docs/DESIGN.md) for the full design.
> The setup steps below describe the planned workflow and don't work yet.

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

## Features (MVP)

- [ ] Resume upload → structured research profile
- [ ] Free-form "Name, School" input with a parse preview
- [ ] Automatic homepage lookup and profile extraction (up to 10 schools)
- [ ] Recruiting status + contact policy, with evidence
- [ ] Interest-based screening with explanations
- [ ] Paper intake from PDFs and web links
- [ ] Per-paper structured summaries
- [ ] Evidence-backed connection points
- [ ] Personalized email drafts with saved versions
- [ ] Outreach tracker with follow-up reminders

## Tech stack

| Layer | Tech |
| --- | --- |
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | FastAPI (Python 3.12), SQLAlchemy, Alembic |
| Database | PostgreSQL 16 + pgvector |
| Parsing | httpx, Playwright (fallback), trafilatura, PyMuPDF |
| Web search | Claude's web search tool, used only to find homepages |
| Paper metadata | Crossref, arXiv, PubMed/PMC, Unpaywall |
| LLM | Claude (`claude-opus-5-5`) via the Anthropic Python SDK |
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

## Getting started (planned)

```bash
git clone https://github.com/xinyuhwang/PhDDog.git
cd PhDDog
cp .env.example .env        # set ANTHROPIC_API_KEY
docker compose up --build
```

- Frontend: <http://localhost:3000>
- API docs: <http://localhost:8000/docs>

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
