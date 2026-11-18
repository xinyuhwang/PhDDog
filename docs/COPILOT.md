# Application Copilot — Design Document

**Status:** Accepted, not built (D28) · **Last updated:** 2026-11-11 · **Owner:** Xinyu Wang

A Chrome extension that helps the applicant fill university application
portals from a single verified profile. It is an extension of PhDDog: it
reuses PhDDog's backend, profile, application tracker, LLM adapter and
grounding checks, and adds what PhDDog lacks: structured facts with
provenance, a document registry, form understanding, and a fill engine.

> Related: [DESIGN.md](DESIGN.md) (the main app) and
> [DECISIONS.md](DECISIONS.md). Decisions C1–C10 (§12) were accepted on
> Nov 11 and are logged as D28.

---

## 1. Overview

### 1.1 The problem

Each program has its own portal, terminology, field layout and
requirements. The same facts (education, test scores, research experience,
recommenders) are typed into every portal by hand, with small
inconsistencies creeping in. The short-answer questions ("Describe your
research interests", 500 characters) look different in each portal but
draw on the same experience.

Filling text fields is not the hard part. The hard part is:
- understanding what an unfamiliar field is asking for, and
- getting the right, consistent, verified answer into it.

### 1.2 Principles

1. **Write once, reuse everywhere.** One profile of verified facts and one
   registry of documents, used by every portal.
2. **Understand before filling.** Map each field to a known meaning before
   putting anything in it. When the meaning is unclear, ask the user.
3. **The applicant decides.** The extension fills and suggests. The
   applicant reviews everything, and always submits, certifies, signs and
   pays by hand.
4. **No invented facts.** Every fact in a filled field or generated answer
   traces to a verified profile record or a document the user supplied.
   This is PhDDog's grounding rule (DESIGN.md §1.3) applied to portals.
5. **Local first, minimal exposure.** Data stays on the user's machine.
   Page content does not leave the browser, and only the facts needed for a
   generated answer go to the LLM.

### 1.3 Goals

- A structured, verified academic profile with a source for every value.
- A side panel on any application portal that shows, for the current page:
  - what can be filled from verified facts,
  - what needs review or an answer,
  - what is missing, conflicting or sensitive.
- Filling of standard field types, with every fill checked afterwards.
- Grounded drafts for short-answer questions, within the portal's limit,
  editable before insertion.
- Per-application state that survives navigation, multi-step forms and
  returning later, tied to PhDDog's existing application tracker.
- A benchmark for measuring detection, mapping, fill and answer quality.

### 1.4 Non-goals

- **Submitting, certifying, signing or paying.** These are always manual.
- **Writing the statement of purpose.** Long statements are uploaded as
  documents in most portals. The applicant writes them; PhDDog already
  helps elsewhere. The Copilot drafts short-answer fields only (C9).
- **Recommendation letters.** The Copilot tracks recommenders and
  invitation status. It never writes, reads or uploads letter content, and
  never acts as a recommender.
- **Getting past portal protections.** No CAPTCHA solving, no automated
  logins, no automated navigation between pages.
- **Per-university adapters at the start** (§2, C4).
- **Multi-user hosting.** Single local user, like PhDDog (DESIGN.md §1.2).

---

## 2. Review of the original proposal

The proposal this doc is based on had four components (Academic Profile,
Application Intelligence, Autofill Engine, Application Tracker), three
principles, and a four-phase roadmap. Most of it holds up. This section
records what was kept, what changed and why.

### 2.1 Kept

- **The three principles** (§1.2, points 1–3).
- **Three data layers:** verified facts, derived values and generated
  content. Verified facts never change without the user's confirmation.
  Generated answers can differ per university.
- **Structured facts with provenance**, not one text blob.
- **Hybrid field mapping:** rules first, the LLM only for ambiguous fields,
  and review below a confidence threshold. A canonical field ontology with
  aliases.
- **Framework-aware filling:** use the native value setter, dispatch input
  and change events, then re-read the field to verify. Never mark a field
  complete just because a script tried to fill it.
- **The edge cases:** multi-step forms, repeated groups, uploads,
  recommenders and sensitive questions.
- **Never submitting.**
- **An evaluation framework**, treating this as an AI engineering problem.
- **Starting with the profile and extension, not the LLM.**

### 2.2 Changed

| # | Original proposal | Change | Why |
| --- | --- | --- | --- |
| 1 | New stack: FastAPI, Postgres, pgvector, OpenAI, Auth.js, AWS | Reuse PhDDog's local backend, Postgres and `llm/` adapter (Claude). No auth service, no AWS. | PhDDog already runs FastAPI, Postgres with pgvector, a job queue, a provider adapter and grounding checks. A second backend would duplicate the profile and the tracker. |
| 2 | Component 4, Application Tracker, built as part of the extension | Extend PhDDog's Applications page (DESIGN.md §4.7) | Deadlines, status, checklists and Do next already exist. The extension adds portal-level progress to them. |
| 3 | Profile stored in extension storage *and* in a backend Profile Service | The backend is the only source of truth. The extension keeps short-lived per-tab state only. | Two copies of the profile drift apart. Extension storage is also a weaker place to hold personal data. |
| 4 | Generic detection first; university adapters only when needed | Same, plus **learned mappings** and **portal vendor profiles** (§5.4) | Many universities run the same commercial portal software. Variation is mostly per vendor, so a confirmed mapping on one school's portal often carries over to another. |
| 5 | Embedding-based semantic matching against the profile schema | Rules, aliases and HTML `autocomplete` tokens, then one LLM call per form section. Embeddings only if the benchmark shows they help. | The ontology has about 100–150 keys. Rules plus a constrained LLM classification cover that; embeddings add a moving part without a measured gain. |
| 6 | Autofill as the first deliverable | **Copy mode first** (§7, Phase 1): the side panel shows the right verified value for each field, and one click copies it | Works on every portal, including custom widgets, with no risk of a bad write. Useful within days, before the fill engine exists. |
| 7 | Retrieval-based generation for "Why this program?" and statements | Short-answer fields only, grounded with a validator (§6), Claude only, and disabled offline | Matches PhDDog's no-fake-results rule (D27). Statement-length writing stays with the applicant. |
| 8 | Content script calls the backend | All network calls go through the background service worker, with a pairing token (§8) | Content-script requests run under the portal's origin and hit CORS and Chrome's local-network protections. PhDDog's API has no auth today, so a token is needed before a browser extension can reach it. |
| 9 | Sensitive questions need explicit review | Sensitive categories are **never filled**, at any confidence (§5.6) | Legal declarations, disciplinary history, visa and immigration status, signatures and payment have no safe automation. |

### 2.3 Gaps the proposal didn't cover

- **Visibility of facts.** Some facts are private: unpublished results,
  project details a supervisor asked to keep confidential. Each fact needs a
  visibility level and, for private work, a user-approved public summary
  (§4.1).
- **Program AI-use policies.** Some programs publish rules on AI help with
  application essays. Record each program's policy with its source, show it
  in the side panel, and turn off drafting where it isn't allowed (§6.4).
- **Formatting conflicts.** A portal may want a GPA to two decimals, a date
  in a different format, or a degree from a fixed list. These are derived
  values. They are shown for review and never rounded or reworded silently.
- **Which application is this?** PhDDog applications already store
  `apply_url`. The side panel matches the portal's host against it.
- **Timing.** Most of the 10 current applications are due Dec 12–15, 2026.
  Phases 0 and 1 can help this cycle. The fill engine (Phase 2) probably
  lands too late for most of them, which is fine for a portfolio project
  but should be planned for.
- **The name.** "Copilot" is a Microsoft product name. Pick a different one
  before any public listing (§12).

---

## 3. Architecture

```text
┌──────────────────── Chrome extension (MV3, TypeScript, React) ────────────────────┐
│                                                                                    │
│  Content script (per portal tab, all frames)       Side panel (React)              │
│   ├─ Field detector (DOM → FieldDescriptor[])       ├─ Application match            │
│   ├─ Mutation watcher (re-detect on change)         ├─ Ready / Review / Answer /    │
│   ├─ Fill handlers + post-fill verification         │  Missing / Conflict /         │
│   └─ never sends page HTML anywhere                 │  Sensitive groups             │
│              │  chrome.runtime messages             ├─ Copy, Fill, Insert answer    │
│              ▼                                      └─ Provenance for each value    │
│  Background service worker                                    ▲                     │
│   ├─ only component that talks to the backend ────────────────┘                     │
│   ├─ pairing token, per-tab session state (chrome.storage.session)                  │
│   └─ optional host permissions, requested per portal                                │
└───────────────────────────────┬────────────────────────────────────────────────────┘
                                │ HTTP + X-PhDDog-Token, localhost only
                                ▼
┌──────────────────── PhDDog backend (existing FastAPI) ─────────────────────────────┐
│  existing: profile · applications (tracker) · schools · professors · jobs · llm/  │
│  new:      facts · documents · copilot (mapping, answers, fill log, recommenders)  │
└───────────────────────────────┬────────────────────────────────────────────────────┘
                                ▼
                 Postgres (+ pgvector)   ·   ./data files   ·   Claude (only when the user
                                                              asks for a draft or a mapping)
```

**Where the work happens**

| Concern | Where | Reason |
| --- | --- | --- |
| Reading the DOM, rules-based field signals | Content script | Page content stays in the browser |
| Ontology, learned mappings, profile values | Backend | One source of truth, shared with the PhDDog UI |
| LLM field classification and drafting | Backend, `llm/` adapter | Same providers, offline rules and grounding as the rest of PhDDog |
| Writing values into the page and verifying them | Content script | Needs the live DOM |
| Approval of every value | Side panel | The applicant decides |

### 3.1 Technology

| Layer | Choice | Notes |
| --- | --- | --- |
| Extension | Chrome Manifest V3, TypeScript, React, Tailwind v4, Vite build | Same UI stack as the PhDDog frontend. Zustand is optional; plain React state is enough to start. |
| Side panel | `chrome.sidePanel` | Stays open while the user works in the page, unlike a popup |
| Per-tab state | `chrome.storage.session` | Cleared when the browser closes. Nothing personal is kept in `chrome.storage.local`. |
| Backend | Existing FastAPI app, new routers | §9 |
| Database | Existing Postgres, new tables | §4 |
| LLM | Existing `llm/` adapter: `fake` offline, `claude` when configured, Claude-session import now | DESIGN.md §7. OpenAI is not added. |
| Documents | Existing PyMuPDF; `python-docx` if a .docx is uploaded | Page count, size, text for provenance |
| Tests | Vitest + jsdom (detector, mapper); Playwright with the unpacked extension on local fixture pages; pytest (backend) | §10 |

---

## 4. Data model (new tables)

All tables follow PhDDog's conventions: UUID `id`, `created_at`,
`updated_at` and `user_id`.

```text
profile_records                     one record = one fact or one repeated-group entry
  kind              ontology group: identity | contact | education | test_score |
                    research_experience | publication | employment | award |
                    skill | reference | program_pref
  ordinal           order within the kind (education #1, #2, …)
  fields            jsonb: { key: { value, source: {document_id?, quote?, page?, url?} } }
  status            extracted | verified | rejected
  visibility        public | application | private
  public_summary    text: the user-approved wording for private work (nullable)
  verified_at, supersedes_id → profile_records (history; a verified record is
                    never edited in place)

documents
  kind              cv | transcript | sop | personal_statement | writing_sample |
                    test_report | other
  label, version, file_path, sha256, mime, size_bytes, page_count
  application_id    → applications (nullable: a program-specific version)
  status            current | superseded

application_portals                 extends applications (1:1)
  application_id → applications, portal_host, vendor (nullable),
  ai_policy (text + source_url), sections (jsonb: [{name, done}])

portal_field_mappings               learned from user confirmations
  vendor (nullable), host, signature, ontology_key, record_ordinal (nullable),
  confirmed (bool), times_used, last_seen_at
  UNIQUE (host, signature)

application_questions               the short-answer questions, per application
  application_id, signature, question_text, ontology_key,
  limit_kind (chars | words | none), limit_value, required

answers
  question_id → application_questions, version, text,
  record_ids (uuid[]: the facts used), generated_by (user | claude | claude-session),
  validation (jsonb: result of §6.3), approved_at, inserted_at, verified_at

fill_events                         audit log; stores a hash of the value, not the value
  application_id, signature, ontology_key, value_sha256,
  result (filled | verified | reverted | failed | rejected_by_user), at

recommenders
  name, title, institution, email, relationship

recommendation_requests
  application_id, recommender_id, invited_at,
  status (not_invited | invited | started | submitted), status_source (user | portal_read),
  last_synced_at
```

### 4.1 Facts, derived values and generated text

| Layer | Example | Stored in | Changes |
| --- | --- | --- | --- |
| Verified fact | "M.S. in Computer Science, GPA 3.9 (4.0 scale)" | `profile_records`, `status = verified` | Only through a new record that the user confirms |
| Derived value | "3.90" for a two-decimal GPA field; "2 years" of research | Computed at fill time from verified facts; never stored as a fact | Shown with its derivation and needs review |
| Generated text | A 500-character answer about research interests | `answers` | Editable per application; must pass §6.3 |

**Visibility**
- `public`: can go anywhere, including LLM prompts.
- `application`: fine in a portal field or a prompt (for example a test
  score), but not in outreach.
- `private`: never leaves the machine and is never sent to the LLM. If the
  user adds a `public_summary` ("lead author of a medical imaging study in
  preparation"), only that summary is used.

**Extraction.** Uploading a CV or transcript creates `extracted` records,
each value with its source quote. The user verifies them on My profile.
Rules extract the regular parts offline (dates, GPA, degree names). The
rest needs Claude, or the user types it.

---

## 5. Form understanding

### 5.1 Field detection (content script)

For every fillable element, including inputs, selects, textareas,
`contenteditable` areas and ARIA widgets (`role="combobox"`,
`listbox`, `radiogroup`, `checkbox`):

```ts
interface FieldDescriptor {
  signature: string;        // stable hash; see §5.2
  frameId: number;          // fields inside iframes are detected too
  kind: "text" | "email" | "tel" | "date" | "number" | "textarea" | "select"
      | "radio" | "checkbox" | "combobox" | "file" | "richtext";
  label: string;            // <label for>, aria-labelledby, aria-label, wrapping label
  name?: string; idAttr?: string; placeholder?: string;
  autocomplete?: string;    // HTML autocomplete token, e.g. "given-name", "email", "bday"
  required: boolean;
  options?: { value: string; text: string }[];
  section?: string;         // nearest heading / fieldset legend
  help?: string;            // aria-describedby or nearby instruction text, truncated
  maxLength?: number; pattern?: string;
  groupIndex?: number;      // position in a repeated group (education #2)
  visible: boolean;
}
```

- **Dynamic pages:** a debounced `MutationObserver`, plus hooks on history
  navigation, re-run detection for the changed subtree only.
- **Frames and shadow DOM:** the content script runs in all frames and
  walks open shadow roots.
- **Repeated groups:** sibling containers with the same field signatures
  form a group. "Add another" buttons are found but **never clicked
  automatically**. The side panel asks first.

### 5.2 Field signature

Element IDs in framework-built portals often change between visits, so the
signature combines more stable signals:

```text
signature = hash( normalize(label) | name-without-numeric-suffix | kind |
                  normalize(section) | hash(sorted option texts) )
```

A changed signature means the mapping is treated as new and reviewed
again. It is never reused on a guess.

### 5.3 Ontology

The ontology is a versioned file in the backend, `app/copilot/ontology.yaml`.

```yaml
- key: education.institution
  group: education          # repeated group
  type: string
  aliases: ["institution", "school name", "college/university", "name of institution"]
  autocomplete: ["organization"]
- key: education.gpa
  group: education
  type: decimal
  aliases: ["gpa", "grade point average", "cumulative gpa"]
  derive: [round_to_field_precision]   # derived value → review
- key: program.research_interests
  type: long_text
  generation: allowed                   # may be drafted (§6)
- key: legal.disciplinary_history
  sensitive: true                       # never filled (§5.6)
```

The first version covers identity, contact, education, tests, research,
publications, employment, awards, references, program preferences,
funding and the sensitive categories.

### 5.4 Mapping pipeline

```text
1. Learned mapping   (host, signature) confirmed before        → confidence 0.95
   Vendor mapping    same vendor, same signature, other host   → 0.85
2. Rules             autocomplete token / alias match on label, name, section;
                     type must be compatible                    → 0.6–0.9
3. LLM               one call per section, for unmapped fields only; output
                     constrained to ontology keys + "unknown"   → model-rated, capped at 0.8
4. Review            below 0.8, or any derived value, or a new signature on a
                     sensitive-adjacent section                 → user decides
```

- Confirming a mapping in the side panel writes it to
  `portal_field_mappings`. The second portal on the same vendor needs far
  fewer decisions. "Write once, reuse everywhere" also applies to mappings.
- The LLM receives only the field descriptors for that section and the
  list of ontology keys. It receives no profile values and no page HTML.
- Offline (`LLM_PROVIDER=fake`), step 3 is skipped and those fields go to
  review.

### 5.5 Values for repeated groups

Education entry *n* on the page maps to the record the user picks. The
default is the order on My profile, most recent first, which is the common
portal order. Mismatched counts are flagged: three entries on the page
versus two records, or a required entry with no record.

### 5.6 Sensitive and manual-only categories

These are never filled, even when confidence is high. The side panel shows
the question with a "You answer this" label:

- legal declarations and certifications, signatures, "I confirm …" boxes;
- disciplinary, academic-integrity or criminal history;
- visa, immigration, citizenship-for-legal-purposes and residency
  declarations;
- government ID numbers (SSN, passport numbers), which are also **never
  stored**;
- payment, fee waivers, and funding commitments;
- consent to share data, and waivers of the right to see letters.

---

## 6. Drafting short answers

### 6.1 What is in scope

Fields whose ontology key allows generation, typically 100–1,500
characters: research interests, research experience summaries, faculty of
interest, "why this program" in short form, and career goals. A
statement-length question with an upload option is shown as a document
slot, not drafted.

### 6.2 Request

```ts
interface DraftRequest {
  questionId: string;
  question: string;
  limit?: { kind: "chars" | "words"; value: number };
  application: { school: string; program: string };
  records: string[];        // ids of facts the user selected, or the default set
  context?: string[];       // from PhDDog: pinned faculty, program notes, admit notes
  instructions?: string;    // the user's own guidance
}
```

- Retrieval is simple on purpose. The default set is the records whose
  kind matches the question's ontology key, plus the user's research
  statement. The user can add or remove records before drafting. This
  stays small and inspectable for one user. Embeddings wait for the
  benchmark (C5).
- Faculty context comes from PhDDog's professors at that school:
  recruiting status, contact status and notes.

### 6.3 Validation before an answer can be inserted

Following the pattern of D21 and D27, checks run in code, not in the model:

1. **Citations:** the output is text plus a list of claims. Each claim
   cites record ids that exist, are verified and are not private.
2. **Numbers, dates and names:** every number, year, date, degree,
   institution, venue and capitalized proper noun in the text must appear
   in a cited record or in the application context. A professor's name
   must be a saved professor at that school, as in the admission-chances
   faculty check.
3. **Length:** counted the way the portal counts (characters including
   spaces, or words). Over the limit fails; it is never truncated silently.
4. **Private data:** no text from `private` records except their
   `public_summary`.

A failed answer is shown with the failing spans highlighted. It can be
edited, but it can't be inserted until it passes or the user marks the
span as their own wording. That override is logged.

### 6.4 Providers and policy

- `claude`: drafts on request, with effort set explicitly (DESIGN.md §7).
- `fake` (offline): drafting is **disabled**. `[FAKE]` text must never
  reach a real portal.
- **Claude session** (now, with no API key): answers written in a Claude
  Code session are imported with `PUT /copilot/answers`, through the same
  validation, `generated_by = claude-session`.
- **AI policy:** if `application_portals.ai_policy` says generated text
  isn't allowed, the Draft button is hidden for that application. The
  panel still shows the facts the user could draw on.

---

## 7. Filling

### 7.1 Handlers

| Kind | How it fills | How it verifies |
| --- | --- | --- |
| text, email, tel, number, textarea | Native prototype `value` setter, then `input`, `change` and `blur` events | Re-read `.value` after a frame and after blur; catches values the framework reverts |
| date (`type=date`) | ISO value through the native setter | Re-read |
| date (text with a mask) | Format from placeholder, pattern or label (MM/DD/YYYY…); typed one key at a time if the mask needs it | Re-read and parse back to the same date |
| select | Exact match on option value or text, then normalized match (case, punctuation, known synonyms such as "Master of Science" = "M.S.") | Selected option text equals the target; no match means review, never the "closest" option |
| radio, checkbox | Click the input whose label matches | `checked` state |
| combobox (custom) | Focus, type, wait for the listbox, pick the matching option with the keyboard | Displayed value and any hidden input |
| richtext / contenteditable | `beforeinput`/`input` events, or `execCommand('insertText')` as a fallback | Visible text |
| file | Only after the user clicks "Attach" for that document: build a `File` from the backend bytes, assign via `DataTransfer` | The portal shows the filename; size and type match the slot's stated rules |

### 7.2 Rules

- **Fill ready fields** fills only fields that are verified-fact,
  confidence ≥ 0.8, non-derived and non-sensitive. Everything else is one
  field at a time.
- An existing non-empty value is never overwritten without asking. The
  panel shows the current and proposed values side by side.
- Every attempt writes a `fill_events` row, with a hash of the value, not
  the value.
- The extension never clicks Next, Save, Submit, "Add another", or any
  button that changes pages or sends data. The user does.

---

## 8. Security and privacy

| Concern | Decision |
| --- | --- |
| Extension ↔ backend | Only the background worker calls the backend, at `http://localhost:<port>`, through `host_permissions`. Every `/copilot`, `/facts` and `/documents` request carries `X-PhDDog-Token`, a random token created when the user pairs the extension from My profile. Requests without it get 401. |
| The existing API has no auth | Phase 1 adds the token check to the new routers and a setting to require it everywhere. Without it, any web page could send simple requests to localhost. |
| Portal permissions | `optional_host_permissions`, requested for each portal host the first time the user opens the side panel there. No `<all_urls>` at install. |
| What leaves the browser | Field descriptors (labels, names, options, help text) go to the local backend. Page HTML, existing field values and other page text never do. |
| What goes to the LLM | For mapping: field descriptors and ontology keys. For drafts: the question, the selected non-private records, and application context. Nothing else. |
| What's stored where | Facts and documents in Postgres and `./data` (gitignored, as today). The extension keeps per-tab state in `chrome.storage.session` only. No government ID numbers anywhere. |
| Benchmark fixtures | Real portal snapshots may contain personal data and vendor code. They stay in `data/` (gitignored). Committed fixtures are synthetic. |
| Distribution | Load unpacked for personal use. A Chrome Web Store listing would need a privacy policy and a different name (§12). |

---

## 9. API (new routes)

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/copilot/pair` | Create a pairing token (from the PhDDog UI only) |
| GET/POST/PATCH | `/facts`, `/facts/{id}` | List, extract from a document, verify, reject or supersede records |
| POST | `/facts/extract` | Extract records from an uploaded document (job) |
| GET/POST | `/documents` | Register a document version; mark it current or superseded |
| GET | `/copilot/match?host=` | Which application this portal belongs to |
| POST | `/copilot/map` | Field descriptors in → mappings with confidence, method and values (derived values flagged) |
| PUT | `/copilot/mappings` | Confirm or correct a mapping (learned mapping) |
| GET/PUT | `/copilot/questions` | The application's short-answer questions |
| POST | `/copilot/answers/draft` | Queue a draft (409 offline, as with admission chances) |
| PUT | `/copilot/answers` | Import or save an answer; runs §6.3 validation |
| POST | `/copilot/fill-events` | Log fill results |
| GET/PUT | `/recommenders`, `/applications/{id}/recommendations` | Recommender tracking |

The existing `GET /applications` gains a portal progress summary.
Applications cards show "Portal: 3 of 7 sections, 2 answers to review".

---

## 10. Evaluation

| Metric | Definition | How measured |
| --- | --- | --- |
| Detection recall | Fillable fields found ÷ fillable fields on the page | Labeled fixture pages |
| Mapping accuracy | Correct ontology key ÷ fields mapped, per method (rules, learned, LLM) | Labeled fixtures; compare rules vs. rules + LLM, and embeddings if tried |
| Abstention quality | Wrong mappings caught by review ÷ all wrong mappings | Fixtures |
| Fill success | Fields verified after filling ÷ fills attempted, per handler | Playwright on fixtures |
| Factual support | Draft claims passing §6.3 ÷ all claims; plus a manual check of a sample | Validator output, hand review |
| Correction rate | Values or answers the user edited ÷ inserted | `fill_events`, `answers` versions |
| Time saved | Minutes per portal section, with and without the extension | Timed on real use |

**Fixtures:**
- Synthetic pages, committed, that copy common portal patterns: masked
  dates, custom comboboxes, repeated education groups, iframes, multi-step
  sections, React-controlled inputs.
- Sanitized snapshots of real portals, kept in `data/` and never committed.

The benchmark is the portfolio part of the project. The interesting result
is the comparison between rules, learned mappings and LLM classification,
with error analysis.

---

## 11. Roadmap

| Phase | Deliverable | Useful for |
| --- | --- | --- |
| **0. Inventory** (days) | For each current application: portal host and vendor, AI-use policy with source, and every short-answer question with its limit, saved in `application_questions`. Count fields on two portals. | This cycle. Short answers can be written in PhDDog now, and the counts size the rest of the work. |
| **1. Facts + copy mode** | `profile_records` with provenance and verification on My profile; document registry; pairing token; side panel that matches the application and lists verified values and approved answers per section, with click-to-copy. No page writes. | This cycle. Consistent values in every portal. |
| **2. Detection + fill** | Field detector, ontology v1, rules and learned mappings, handlers and verification for text, textarea, select, date, radio and checkbox; review UI; sensitive categories; fill log; synthetic fixtures with tests. | The Jan 5 deadline and later; the core engineering. |
| **3. Drafts + LLM mapping** | Grounded drafting with §6.3 validation (Claude, Claude-session import), LLM section classification, AI-policy gating. | Short answers. |
| **4. Recommenders, documents, benchmark** | Recommendation status (manual, plus read-only sync from the portal page the user has open), document version checks at upload, the full benchmark report. | The portfolio write-up. |

The tracker is not a phase. It already exists, and each phase adds to it.

---

## 12. Decisions (accepted Nov 11, D28)

| # | Decision |
| --- | --- |
| C1 | The extension is a client of PhDDog's local backend. There is no separate stack, auth service or cloud deployment. |
| C2 | The backend is the only store of profile data. The extension keeps per-tab state in `chrome.storage.session` only. |
| C3 | Facts are `profile_records` with provenance, verification, visibility and history. Derived values are computed, never stored as facts, and always reviewed. |
| C4 | Generic detection, plus learned mappings keyed by host and signature, shared across a portal vendor. No per-university code until a portal can't be handled otherwise. |
| C5 | Mapping uses rules, then learned mappings, then one constrained LLM call per section. No embeddings until the benchmark shows a gain. |
| C6 | Copy mode ships before the fill engine. |
| C7 | The extension never submits, certifies, signs, pays, navigates, clicks "Add another", or fills a sensitive category. |
| C8 | Only the background worker talks to the backend, with a pairing token. Page HTML never leaves the browser. |
| C9 | Drafting covers short-answer fields only, validated in code; disabled offline and where a program's AI policy forbids it. |
| C10 | Benchmark fixtures from real portals stay in `data/`; committed fixtures are synthetic. |

### Open questions

| Question | Options | Lean |
| --- | --- | --- |
| Name | "Copilot" (a Microsoft product name) / PhDDog Apply / another | Rename before any public listing |
| Drafting "Why this program?" | Short answers only / also statement-length | Short answers only (C9) |
| Scope beyond this user | Personal tool and portfolio / product for other applicants | Personal tool. Multi-user would need auth, hosting and a privacy review. |
| First portal to support | The one with the nearest deadline / the most common vendor among the 10 | Decided by Phase 0 |
| Shared TypeScript types with the frontend | Hand-mirrored (as `frontend/src/lib/api.ts` is today) / generated from OpenAPI | Generate them once the API settles |

---

## 13. Risks

| Risk | Mitigation |
| --- | --- |
| A wrong value goes into a submitted application | Review states, no overwriting without asking, verification after filling, the applicant submits by hand, and the panel shows unresolved items before the user leaves a section |
| A portal changes its markup | Signatures change, so mappings go back to review instead of being misapplied; fixtures catch regressions |
| The LLM invents a fact | Constrained outputs, citation checks, entity and number checks, private-data checks; drafting off offline |
| Personal data leaks | Local backend, pairing token, optional host permissions, nothing in persistent extension storage, no ID numbers stored |
| A portal's terms or a program's AI policy | User-driven filling in the user's own browser, no automated navigation or submission, AI policy recorded per program and enforced |
| Building it competes with finishing applications | Phases 0–1 are small and help this cycle; Phases 2–4 are scheduled after the December deadlines |
