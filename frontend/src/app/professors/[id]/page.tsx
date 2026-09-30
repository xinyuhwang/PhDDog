"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { Badge, Button, Card, ContactBadge, ErrorNote, FitBadge, inputClass, Quote, RecruitingBadge, ResolveBadge, StageBadge } from "@/components/ui";
import { api, type Job, type ProfessorDetail } from "@/lib/api";
import { useApi, useShowFit } from "@/lib/hooks";

import EmailPanel from "./EmailPanel";
import PapersPanel from "./PapersPanel";

export default function ProfessorPage() {
  const { id } = useParams<{ id: string }>();
  const jobs = useApi<Job[]>("/jobs", (d) => d.some((j) => j.status !== "failed" && j.payload.professor_id === id));
  const busy = !!jobs.data?.some((j) => j.status !== "failed" && j.payload.professor_id === id);
  const { data: prof, error, reload } = useApi<ProfessorDetail>(`/professors/${id}`, (p) => p.resolve_status === "pending" || busy);
  const [editing, setEditing] = useState(false);
  const showFit = useShowFit();

  if (error) return <ErrorNote error={error} />;
  if (!prof) return <p className="text-sm text-stone-500">Loading…</p>;

  const refreshJobs = () => { jobs.reload(); reload(); };
  const setStatus = async (status: string) => { await api.patch(`/professors/${id}`, { status }); reload(); };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/professors" className="text-sm text-indigo-600 hover:underline">← Professors</Link>
          <h1 className="mt-1 text-2xl font-semibold">{prof.name}</h1>
          <p className="text-sm text-stone-600">{[prof.title, prof.department, prof.school_name].filter(Boolean).join(" · ")}</p>
          <div className="mt-2 flex flex-wrap gap-3 text-sm">
            {prof.homepage_url && <a className="text-indigo-600 hover:underline" href={prof.homepage_url} target="_blank" rel="noreferrer">Homepage ↗</a>}
            {prof.lab_url && <a className="text-indigo-600 hover:underline" href={prof.lab_url} target="_blank" rel="noreferrer">Lab ↗</a>}
            {prof.email && <span className="text-stone-700">{prof.email}</span>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ResolveBadge status={prof.resolve_status} />
          <StageBadge status={prof.status} />
          {["added", "resolved", "screened"].includes(prof.status) && <Button onClick={() => setStatus("shortlisted")}>☆ Shortlist</Button>}
          {prof.status === "shortlisted" && <Button variant="secondary" onClick={() => setStatus("screened")}>★ Shortlisted</Button>}
          {prof.status !== "dismissed"
            ? <Button variant="secondary" onClick={() => setStatus("dismissed")}>Dismiss</Button>
            : <Button variant="secondary" onClick={() => setStatus("screened")}>Restore</Button>}
          <Button variant="secondary" disabled={!prof.homepage_url || busy} onClick={async () => { await api.post(`/professors/${id}/refresh`); refreshJobs(); }}>
            {busy ? "Working…" : "Re-check site"}
          </Button>
        </div>
      </div>

      {prof.resolve_status !== "resolved" && <ResolvePanel prof={prof} onChanged={refreshJobs} />}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Recruiting & contact policy">
          <div className="space-y-4">
            <div>
              <div className="mb-1 flex items-center gap-2 text-sm font-medium">Recruiting <RecruitingBadge status={prof.recruiting_status} cycle={prof.recruiting_cycle} stale={prof.recruiting_stale} /></div>
              {prof.recruiting_evidence ? <Quote text={prof.recruiting_evidence} url={prof.recruiting_source_url} /> : <p className="text-sm text-stone-500">No recruiting statement found on their site.</p>}
            </div>
            <div>
              <div className="mb-1 flex items-center gap-2 text-sm font-medium">Contact policy <ContactBadge policy={prof.contact_policy} /></div>
              {prof.contact_evidence ? <Quote text={prof.contact_evidence} url={prof.contact_source_url} /> : <p className="text-sm text-stone-500">No contact policy found.</p>}
            </div>
            <p className="text-xs text-stone-500">
              Checked {prof.pages.filter((p) => p.fetch_status === "ok").length} page(s)
              {prof.last_checked_at && ` · ${new Date(prof.last_checked_at).toLocaleString()}`}
              {prof.pages.some((p) => p.fetch_status !== "ok") && ` · ${prof.pages.filter((p) => p.fetch_status !== "ok").length} failed`}
            </p>
          </div>
        </Card>

        <Card title="Research" actions={<Button variant="secondary" onClick={() => setEditing(!editing)}>{editing ? "Close" : "Edit details"}</Button>}>
          {editing ? <EditDetails prof={prof} onSaved={() => { setEditing(false); reload(); }} /> : (
            <div className="space-y-3 text-sm">
              {showFit && (
                <div className="flex items-center gap-2"><span className="font-medium">Fit</span><FitBadge label={prof.screen?.label} reason={prof.screen?.reason} />
                  {prof.screen && <span className="text-xs text-stone-500">{prof.screen.reason}</span>}</div>
              )}
              <p className="text-stone-700">{prof.stated_interests ?? <span className="text-stone-400">No research interests extracted.</span>}</p>
              {prof.bio_summary && <p className="text-stone-500">{prof.bio_summary}</p>}
              {prof.user_overrides.length > 0 && <p className="text-xs text-stone-500">Edited by you (kept on re-check): {prof.user_overrides.join(", ")}</p>}
            </div>
          )}
        </Card>
      </div>

      {prof.recent_publications.length > 0 && (
        <Card title="Recent publications found on their site">
          <p className="mb-2 text-xs text-stone-500">Suggestions only. Paste a paper&apos;s link (or upload its PDF) below to analyze it.</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-stone-700">
            {prof.recent_publications.map((p, i) => <li key={i}>{p.title}</li>)}
          </ul>
        </Card>
      )}

      <PapersPanel professorId={id} onJob={refreshJobs} busy={busy} />
      <EmailPanel prof={prof} onChanged={reload} />
    </div>
  );
}

function ResolvePanel({ prof, onChanged }: { prof: ProfessorDetail; onChanged: () => void }) {
  const [url, setUrl] = useState("");
  const choose = async (u: string) => { await api.post(`/professors/${prof.id}/homepage`, { url: u }); setUrl(""); onChanged(); };
  if (prof.resolve_status === "pending") return <Card><p className="text-sm text-stone-600">Finding and reading their homepage…</p></Card>;
  return (
    <Card title="Which homepage is right?">
      <p className="mb-3 text-sm text-stone-600">{prof.resolve_error}</p>
      {prof.candidates.length > 0 && (
        <ul className="mb-4 space-y-2">
          {prof.candidates.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-3 text-sm">
              <a href={c.url} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">{c.url}</a>
              {c.confidence !== null && <Badge>{Math.round(c.confidence * 100)}% match</Badge>}
              <span className="text-stone-500">{c.reason}</span>
              <Button variant="secondary" onClick={() => choose(c.url)}>Use this</Button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <input className={inputClass} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Paste the homepage URL" />
        <Button disabled={!url} onClick={() => choose(url)}>Use URL</Button>
      </div>
    </Card>
  );
}

function EditDetails({ prof, onSaved }: { prof: ProfessorDetail; onSaved: () => void }) {
  const fields = ["title", "department", "email", "lab_url", "stated_interests"] as const;
  const [form, setForm] = useState(() => Object.fromEntries(fields.map((f) => [f, prof[f] ?? ""])) as Record<(typeof fields)[number], string>);
  const [error, setError] = useState<string | null>(null);
  async function save() {
    const changes = Object.fromEntries(fields.filter((f) => form[f] !== (prof[f] ?? "")).map((f) => [f, form[f] || null]));
    try {
      await api.patch(`/professors/${prof.id}`, changes);
      onSaved();
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <div className="space-y-3 text-sm">
      {fields.map((f) => (
        <label key={f} className="block">
          <span className="mb-1 block font-medium capitalize">{f.replace("_", " ")}</span>
          {f === "stated_interests"
            ? <textarea className={`${inputClass} h-28`} value={form[f]} onChange={(e) => setForm({ ...form, [f]: e.target.value })} />
            : <input className={inputClass} value={form[f]} onChange={(e) => setForm({ ...form, [f]: e.target.value })} />}
        </label>
      ))}
      <p className="text-xs text-stone-500">Fields you edit are kept when the site is re-checked.</p>
      <Button onClick={save}>Save</Button>
      <ErrorNote error={error} />
    </div>
  );
}
