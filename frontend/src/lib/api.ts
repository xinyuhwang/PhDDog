export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: (path: string) => request<void>(path, { method: "DELETE" }),
  upload: <T>(path: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<T>(path, { method: "POST", body: form });
  },
};

// --- types (mirror backend/app/api/schemas.py) ---

export type StructuredProfile = {
  interests: string[];
  methods: string[];
  domains: string[];
  skills: string[];
  experiences: { title: string; description: string }[];
  publications: string[];
};

export type Profile = {
  version: number;
  resume_file_path: string | null;
  resume_text: string | null;
  research_statement: string | null;
  keywords: string[];
  structured_profile: StructuredProfile | null;
  created_at: string;
};

export type ParsedEntry = {
  raw: string;
  name: string | null;
  school_raw: string | null;
  department_raw: string | null;
  url: string | null;
  issues: string[];
};

export type Screen = { score: number; label: "strong" | "possible" | "no"; reason: string; profile_version: number };

export type ProfessorSummary = {
  id: string;
  name: string;
  school_name: string;
  department: string | null;
  title: string | null;
  email: string | null;
  homepage_url: string | null;
  resolve_status: "pending" | "resolved" | "needs_review" | "not_found";
  resolve_error: string | null;
  recruiting_status: string;
  recruiting_cycle: string | null;
  recruiting_stale: boolean;
  recruiting_confidence: "high" | "medium" | "low" | null;
  contact_policy: string;
  last_checked_at: string | null;
  check_stale: boolean;
  notes: string | null;
  status: string;
  screen: Screen | null;
};

export type Candidate = { id: string; url: string; source: string; confidence: number | null; reason: string | null; chosen: boolean };

export type ProfessorDetail = ProfessorSummary & {
  input_raw: string | null;
  lab_url: string | null;
  scholar_url: string | null;
  resolve_confidence: number | null;
  stated_interests: string | null;
  bio_summary: string | null;
  recent_publications: { title: string; year: number | null; url: string | null }[];
  recruiting_evidence: string | null;
  recruiting_source_url: string | null;
  contact_evidence: string | null;
  contact_source_url: string | null;
  field_sources: Record<string, string>;
  user_overrides: string[];
  evidence: Evidence[];
  candidates: Candidate[];
  pages: { url: string; kind: string; fetch_status: string; error: string | null; fetched_at: string | null }[];
};

export type Evidence = {
  id: string;
  kind: "recruiting" | "contact_policy";
  claim: string;
  cycle: string | null;
  quote: string;
  source_url: string;
  source_type: string;
  page_updated_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
  gone_at: string | null;
  extractor: string;
  verified: boolean;
};

export type PaperSummary = {
  problem: string;
  methods: string[];
  data_modalities: string[];
  application_setting: string;
  key_findings: string[];
  limitations: string[];
  future_work: string[];
};

export type Paper = {
  id: string;
  source_type: "pdf" | "url";
  source_url: string | null;
  title: string | null;
  authors: string[];
  year: number | null;
  venue: string | null;
  doi: string | null;
  abstract: string | null;
  text_status: "pending" | "full" | "abstract_only" | "failed";
  error: string | null;
  summary: PaperSummary | null;
  text_chars: number;
  year_warning: boolean;
  created_at: string;
};

export type ConnectionPoint = {
  id: string;
  paper_id: string;
  paper_title: string | null;
  kind: "method_overlap" | "domain_overlap" | "future_work_hook";
  paper_evidence: string;
  user_evidence: string;
  explanation: string;
  selected: boolean;
};

export type Draft = {
  id: string;
  version: number;
  subject: string;
  body: string;
  tone: string;
  ask: string;
  connection_point_ids: string[];
  model: string | null;
  edited_by_user: boolean;
  created_at: string;
};

export type Outreach = {
  id: string;
  professor_id: string;
  professor_name: string | null;
  school_name: string | null;
  sent_at: string;
  to_address: string | null;
  subject: string;
  body: string;
  status: string;
  follow_up_at: string | null;
  notes: string | null;
};

export type Job = { id: string; kind: string; status: string; attempts: number; error: string | null; payload: Record<string, string> };

export type Health = { ok: boolean; llm_provider: string; target_cycle: string };
