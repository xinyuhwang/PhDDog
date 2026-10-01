"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge, Button, Card, ContactBadge, ErrorNote, inputClass, RecruitingBadge } from "@/components/ui";
import { api, type Application, type AppStep, type School, type TodoItem } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const STATUS: Record<string, string> = {
  planning: "Planning", in_progress: "In progress", submitted: "Submitted", interview: "Interview",
  admitted: "Admitted 🎉", waitlisted: "Waitlisted", rejected: "Rejected", withdrawn: "Withdrawn",
};
const REQ_LABEL: Record<string, string> = { gre: "GRE", letters: "Letters", fee: "Fee", english: "English test" };

const fmt = (d: string | null) => (d ? new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—");
const daysUntil = (d: string | null) => (d ? Math.round((new Date(`${d}T12:00:00`).getTime() - Date.now()) / 86_400_000) : null);

function DueBadge({ date, done }: { date: string | null; done?: boolean }) {
  const n = daysUntil(date);
  if (done || n === null) return null;
  if (n < 0) return <Badge tone="red">{-n}d overdue</Badge>;
  if (n === 0) return <Badge tone="red">today</Badge>;
  if (n <= 7) return <Badge tone="yellow">in {n}d</Badge>;
  return <Badge>in {n}d</Badge>;
}

export default function ApplicationsPage() {
  const apps = useApi<Application[]>("/applications");
  const todo = useApi<TodoItem[]>("/applications/todo?limit=10");
  const schools = useApi<School[]>("/schools");
  const reload = () => { apps.reload(); todo.reload(); };

  const withApp = new Set(apps.data?.map((a) => a.school_id));
  const missing = schools.data?.filter((s) => s.is_target && !withApp.has(s.id)) ?? [];
  const active = apps.data?.filter((a) => ["planning", "in_progress"].includes(a.status)) ?? [];
  const totals = active.reduce((t, a) => ({ left: t.left + a.remaining, overdue: t.overdue + a.overdue, soon: t.soon + a.due_soon }),
    { left: 0, overdue: 0, soon: 0 });
  const nextDeadline = active.filter((a) => a.deadline).sort((a, b) => a.deadline!.localeCompare(b.deadline!))[0];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          ["Applications", apps.data?.length ?? 0],
          ["Steps left", totals.left],
          ["Overdue / due this week", `${totals.overdue} / ${totals.soon}`],
          ["Next deadline", nextDeadline ? `${nextDeadline.school_name.replace("University of ", "U. ")} · ${fmt(nextDeadline.deadline)}` : "—"],
        ].map(([label, value]) => (
          <div key={label as string} className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
            <div className={`font-semibold ${label === "Next deadline" ? "text-sm" : "text-2xl"}`}>{value}</div>
            <div className="text-sm text-stone-500">{label}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card title="Do next" actions={<span className="text-xs text-stone-500">Across all active applications, most urgent first</span>}>
            {!todo.data?.length ? <p className="text-sm text-stone-500">Nothing pending. Add an application below to get a checklist.</p> : (
              <ul className="divide-y divide-stone-100">
                {todo.data.map((t) => (
                  <li key={t.step.id} className="flex items-center gap-3 py-2 text-sm">
                    <input type="checkbox" onChange={async () => { await api.patch(`/application-steps/${t.step.id}`, { done: true }); reload(); }} />
                    <span className="flex-1">{t.step.label}<span className="text-stone-500"> · {t.school_name} — {t.program}</span></span>
                    <span className="text-xs text-stone-500">{fmt(t.due)}</span>
                    <DueBadge date={t.due} />
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        <AddApplication schools={schools.data ?? []} onAdded={() => { reload(); schools.reload(); }} />
      </div>

      {missing.length > 0 && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
          No application yet for: {missing.map((s) => s.name).join(", ")}. Add one with the form above.
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {apps.data?.map((a) => <ApplicationCard key={a.id} app={a} onChanged={reload} />)}
      </div>
      {apps.data && !apps.data.length && (
        <p className="text-sm text-stone-500">No applications yet. Pick your schools on <Link href="/profile" className="text-indigo-600 hover:underline">My profile</Link>, then add programs here.</p>
      )}
    </div>
  );
}

function AddApplication({ schools, onAdded }: { schools: School[]; onAdded: () => void }) {
  const [schoolId, setSchoolId] = useState("");
  const [program, setProgram] = useState("");
  const [deadline, setDeadline] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const sorted = [...schools].sort((a, b) => Number(b.is_target) - Number(a.is_target) || a.name.localeCompare(b.name));

  async function add() {
    setError(null);
    try {
      await api.post("/applications", { school_id: schoolId, program, deadline: deadline || null, apply_url: url || null });
      setProgram(""); setDeadline(""); setUrl("");
      onAdded();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <Card title="Add application">
      <div className="space-y-2 text-sm">
        <select className={inputClass} value={schoolId} onChange={(e) => setSchoolId(e.target.value)}>
          <option value="">Choose a school…</option>
          {sorted.map((s) => <option key={s.id} value={s.id}>{s.is_target ? "★ " : ""}{s.name}</option>)}
        </select>
        <input className={inputClass} value={program} onChange={(e) => setProgram(e.target.value)} placeholder="Program, e.g. Computer Science PhD" />
        <label className="block text-xs text-stone-600">Deadline
          <input type="date" className={`${inputClass} mt-1`} value={deadline} onChange={(e) => setDeadline(e.target.value)} />
        </label>
        <input className={inputClass} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Application link (optional)" />
        <Button disabled={!schoolId || !program.trim()} onClick={add}>Add with standard checklist</Button>
        <p className="text-xs text-stone-500">Creates 11 steps (letters, SOP, scores, …) with due dates counted back from the deadline. Edit them anytime.</p>
        <ErrorNote error={error} />
      </div>
    </Card>
  );
}

function ApplicationCard({ app, onChanged }: { app: Application; onChanged: () => void }) {
  const [showAll, setShowAll] = useState(false);
  const [newStep, setNewStep] = useState("");
  const pct = app.total ? Math.round((app.done / app.total) * 100) : 0;
  const open = app.steps.filter((s) => !s.done).sort((a, b) => (a.effective_due ?? "9999").localeCompare(b.effective_due ?? "9999"));
  const steps = showAll ? app.steps : open.slice(0, 4);

  const patch = async (body: object) => { await api.patch(`/applications/${app.id}`, body); onChanged(); };
  const toggle = async (s: AppStep) => { await api.patch(`/application-steps/${s.id}`, { done: !s.done }); onChanged(); };

  return (
    <Card
      title={<span>{app.school_name}<span className="block text-sm font-normal text-stone-600">{app.program}</span></span>}
      actions={
        <select className={`${inputClass} w-36 py-1 text-xs`} value={app.status} onChange={(e) => patch({ status: e.target.value })}>
          {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      }
    >
      <div className="space-y-4 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">Deadline</span>
          <input type="date" className={`${inputClass} w-40 py-1`} value={app.deadline ?? ""} onChange={(e) => patch({ deadline: e.target.value || null })} />
          <DueBadge date={app.deadline} />
          {app.deadline_cycle === "previous" && (
            <Badge tone="yellow" title="Only last cycle's date was posted when checked">last year&apos;s date — confirm for Fall 2027</Badge>
          )}
          {app.deadline_cycle === "unknown" && (
            <Badge title="The page gives a recurring date (e.g. 'December 15') without a year">year not stated on page</Badge>
          )}
        </div>
        {app.deadline_text && <p className="text-xs italic text-stone-500">“{app.deadline_text}”</p>}
        <div className="flex flex-wrap gap-3 text-sm">
          {app.apply_url && <a href={app.apply_url} target="_blank" rel="noreferrer" className="font-medium text-indigo-600 hover:underline">Apply ↗</a>}
          {app.deadline_source_url && <a href={app.deadline_source_url} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">Deadline source ↗</a>}
        </div>
        {Object.keys(app.requirements).length > 0 && (
          <div className="flex flex-wrap gap-1">
            {Object.entries(app.requirements).filter(([k, v]) => v && REQ_LABEL[k] && v !== "unknown").map(([k, v]) => (
              <Badge key={k} title={v}>{REQ_LABEL[k]}: {v.length > 40 ? `${v.slice(0, 40)}…` : v}</Badge>
            ))}
          </div>
        )}
        {app.requirements.faculty_in_app && app.requirements.faculty_in_app !== "unknown" && (
          <p className="text-xs text-stone-600"><span className="font-medium">Naming faculty: </span>{app.requirements.faculty_in_app}</p>
        )}

        <div>
          <div className="mb-1 flex justify-between text-xs text-stone-600">
            <span>{app.done} of {app.total} steps done</span>
            <span>{app.remaining} left{app.overdue ? ` · ${app.overdue} overdue` : ""}{app.due_soon ? ` · ${app.due_soon} due this week` : ""}</span>
          </div>
          <div className="h-2 rounded-full bg-stone-100"><div className="h-2 rounded-full bg-indigo-500" style={{ width: `${pct}%` }} /></div>
        </div>

        <ul className="space-y-1">
          {steps.map((s) => (
            <li key={s.id} className="flex items-center gap-2">
              <input type="checkbox" checked={s.done} onChange={() => toggle(s)} />
              <span className={`flex-1 ${s.done ? "text-stone-400 line-through" : ""}`}>{s.label}</span>
              <span className="text-xs text-stone-400">{fmt(s.effective_due)}</span>
              <DueBadge date={s.effective_due} done={s.done} />
              {showAll && (
                <button className="text-xs text-stone-300 hover:text-rose-600" title="Remove step"
                  onClick={async () => { await api.del(`/application-steps/${s.id}`); onChanged(); }}>✕</button>
              )}
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-2">
          <button className="text-xs text-indigo-600 hover:underline" onClick={() => setShowAll(!showAll)}>
            {showAll ? "Show next steps only" : `Show all ${app.total} steps`}
          </button>
          {showAll && (
            <>
              <input className={`${inputClass} flex-1 py-1 text-xs`} value={newStep} onChange={(e) => setNewStep(e.target.value)} placeholder="Add a step" />
              <Button variant="secondary" disabled={!newStep.trim()}
                onClick={async () => { await api.post(`/applications/${app.id}/steps`, { label: newStep }); setNewStep(""); onChanged(); }}>Add</Button>
            </>
          )}
        </div>

        <div>
          <div className="mb-1 font-medium">Faculty to name in this application</div>
          {app.faculty.length ? (
            <ul className="space-y-1">
              {app.faculty.map((f) => (
                <li key={f.id} className="flex flex-wrap items-center gap-2">
                  <Link href={`/professors/${f.id}`} className="text-indigo-600 hover:underline">{f.name}</Link>
                  <RecruitingBadge status={f.recruiting_status} />
                  <ContactBadge policy={f.contact_policy} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-stone-500">Pin professors at {app.school_name} (📌 on the <Link href="/professors" className="text-indigo-600 hover:underline">Professors</Link> page) to list them here.</p>
          )}
        </div>

        <textarea className={`${inputClass} h-16 text-xs`} defaultValue={app.notes ?? ""} placeholder="Notes (portal login hint, recommenders, …)"
          onBlur={(e) => e.target.value !== (app.notes ?? "") && patch({ notes: e.target.value })} />
        <button className="text-xs text-stone-400 hover:text-rose-600"
          onClick={async () => { if (confirm(`Delete the ${app.program} application at ${app.school_name}?`)) { await api.del(`/applications/${app.id}`); onChanged(); } }}>
          Delete application
        </button>
      </div>
    </Card>
  );
}
