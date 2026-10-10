"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge, Button, Card, ErrorNote, inputClass } from "@/components/ui";
import { api, type OutreachTask, type ProfessorSummary } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const fmt = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
const daysUntil = (d: string) => Math.round((new Date(`${d}T12:00:00`).getTime() - Date.now()) / 86_400_000);

function DueBadge({ date, done }: { date: string | null; done: boolean }) {
  if (!date || done) return null;
  const n = daysUntil(date);
  if (n < 0) return <Badge tone="red">{-n}d overdue</Badge>;
  if (n === 0) return <Badge tone="red">today</Badge>;
  return <Badge tone={n <= 7 ? "yellow" : "gray"}>in {n}d</Badge>;
}

/**
 * To-do tasks for outreach: steps to tick off, links, and what to mention.
 * With `professorId`, shows only that professor's open tasks (used on the professor page).
 */
export default function OutreachTasks({ professorId }: { professorId?: string }) {
  const tasks = useApi<OutreachTask[]>(professorId ? `/outreach-tasks?professor_id=${professorId}` : "/outreach-tasks");
  const [adding, setAdding] = useState(false);
  const [showDone, setShowDone] = useState(false);

  const open = tasks.data?.filter((t) => !t.done) ?? [];
  const done = tasks.data?.filter((t) => t.done) ?? [];
  if (professorId && !open.length) return null;

  // Group open tasks by professor; tasks with no professor go under "General" at the end.
  const groups = new Map<string, OutreachTask[]>();
  for (const t of open) {
    const key = t.professor_id ?? "";
    groups.set(key, [...(groups.get(key) ?? []), t]);
  }
  const ordered = [...groups.entries()].sort(([a], [b]) => Number(a === "") - Number(b === ""));

  return (
    <Card title={professorId ? `To do (${open.length})` : `To do (${open.length} open)`}
      actions={professorId
        ? <Link href="/outreach" className="text-sm text-indigo-600 hover:underline">All tasks →</Link>
        : <Button variant="secondary" onClick={() => setAdding(!adding)}>{adding ? "Close" : "+ Add task"}</Button>}>
      {adding && <TaskForm onSaved={() => { setAdding(false); tasks.reload(); }} />}
      {!open.length && !adding && <p className="text-sm text-stone-500">Nothing to do. Add a task for a professor you&apos;re contacting.</p>}
      <div className="space-y-6">
        {ordered.map(([key, list]) => (
          <div key={key || "general"}>
            {!professorId && (
              <h3 className="mb-2 text-sm font-semibold text-stone-700">
                {key ? <Link href={`/professors/${key}`} className="hover:text-indigo-700">{list[0].professor_name}</Link> : "General"}
                {key && <span className="font-normal text-stone-500"> · {list[0].school_name}</span>}
              </h3>
            )}
            <div className="space-y-3">{list.map((t) => <TaskCard key={t.id} task={t} onChanged={tasks.reload} />)}</div>
          </div>
        ))}
      </div>
      {!professorId && done.length > 0 && (
        <div className="mt-6">
          <button className="text-sm text-stone-500 hover:text-stone-700" onClick={() => setShowDone(!showDone)}>
            {showDone ? "▾" : "▸"} Done ({done.length})
          </button>
          {showDone && <div className="mt-3 space-y-3 opacity-70">{done.map((t) => <TaskCard key={t.id} task={t} onChanged={tasks.reload} />)}</div>}
        </div>
      )}
    </Card>
  );
}

function TaskCard({ task, onChanged }: { task: OutreachTask; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const patch = async (body: Partial<OutreachTask>) => { await api.patch(`/outreach-tasks/${task.id}`, body); onChanged(); };
  const toggleStep = (i: number) => patch({ steps: task.steps.map((s, j) => (j === i ? { ...s, done: !s.done } : s)) });
  const left = task.steps.filter((s) => !s.done).length;

  if (editing) return <div className="rounded-md border border-stone-200 p-3"><TaskForm task={task} onSaved={() => { setEditing(false); onChanged(); }} onCancel={() => setEditing(false)} /></div>;

  return (
    <div className="rounded-md border border-stone-200 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`font-medium ${task.done ? "line-through" : ""}`}>{task.title}</span>
        <DueBadge date={task.due_date} done={task.done} />
        {task.due_date && <span className="text-xs text-stone-500">{fmt(task.due_date)}</span>}
        {task.steps.length > 0 && <span className="text-xs text-stone-500">{task.steps.length - left}/{task.steps.length} steps</span>}
        <span className="ml-auto flex gap-1">
          <Button variant="secondary" onClick={() => setEditing(true)}>Edit</Button>
          <Button variant="secondary" onClick={() => patch({ done: !task.done })}>{task.done ? "Reopen" : "Mark done"}</Button>
          <Button variant="danger" onClick={async () => { if (confirm(`Delete "${task.title}"?`)) { await api.del(`/outreach-tasks/${task.id}`); onChanged(); } }}>Delete</Button>
        </span>
      </div>
      {task.steps.length > 0 && (
        <ol className="mt-2 space-y-1">
          {task.steps.map((s, i) => (
            <li key={i} className="flex items-start gap-2">
              <input type="checkbox" className="mt-1" checked={s.done} onChange={() => toggleStep(i)} />
              <span className={s.done ? "text-stone-400 line-through" : "text-stone-700"}>{s.text}</span>
            </li>
          ))}
        </ol>
      )}
      {task.links.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          {task.links.map((l, i) => <a key={i} href={l.url} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">{l.label} ↗</a>)}
        </div>
      )}
      {task.notes && <p className="mt-2 whitespace-pre-wrap rounded-md bg-amber-50/70 px-3 py-2 text-stone-700">{task.notes}</p>}
    </div>
  );
}

/** Steps: one per line. Links: one per line as "Label | URL" (a bare URL works too). */
function TaskForm({ task, onSaved, onCancel }: { task?: OutreachTask; onSaved: () => void; onCancel?: () => void }) {
  const profs = useApi<ProfessorSummary[]>("/professors");
  const [title, setTitle] = useState(task?.title ?? "");
  const [professorId, setProfessorId] = useState(task?.professor_id ?? "");
  const [due, setDue] = useState(task?.due_date ?? "");
  const [steps, setSteps] = useState(task?.steps.map((s) => s.text).join("\n") ?? "");
  const [links, setLinks] = useState(task?.links.map((l) => `${l.label} | ${l.url}`).join("\n") ?? "");
  const [notes, setNotes] = useState(task?.notes ?? "");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    // Keep the done state of steps whose text didn't change.
    const wasDone = new Map(task?.steps.map((s) => [s.text, s.done]));
    const body = {
      title: title.trim(),
      professor_id: professorId || null,
      due_date: due || null,
      steps: steps.split("\n").map((s) => s.trim()).filter(Boolean).map((text) => ({ text, done: wasDone.get(text) ?? false })),
      links: links.split("\n").map((s) => s.trim()).filter(Boolean).map((line) => {
        const [label, url] = line.includes("|") ? line.split("|").map((x) => x.trim()) : [line, line];
        return { label: label || url, url };
      }),
      notes: notes.trim() || null,
    };
    try {
      await (task ? api.patch(`/outreach-tasks/${task.id}`, body) : api.post("/outreach-tasks", body));
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const sorted = [...(profs.data ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  return (
    <div className="mb-4 space-y-2 text-sm">
      <input className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Task, e.g. Finish the warm-up task" />
      <div className="flex flex-wrap gap-2">
        <select className={`${inputClass} flex-1`} value={professorId} onChange={(e) => setProfessorId(e.target.value)}>
          <option value="">General (no professor)</option>
          {sorted.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.school_name}</option>)}
        </select>
        <input type="date" className={`${inputClass} w-44`} value={due} onChange={(e) => setDue(e.target.value)} />
      </div>
      <textarea className={`${inputClass} h-24`} value={steps} onChange={(e) => setSteps(e.target.value)} placeholder="Steps, one per line" />
      <textarea className={`${inputClass} h-16`} value={links} onChange={(e) => setLinks(e.target.value)} placeholder="Links, one per line: Label | https://…" />
      <textarea className={`${inputClass} h-16`} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes: anything to remember or mention" />
      <div className="flex gap-2">
        <Button disabled={!title.trim()} onClick={save}>{task ? "Save" : "Add task"}</Button>
        {onCancel && <Button variant="secondary" onClick={onCancel}>Cancel</Button>}
      </div>
      <ErrorNote error={error} />
    </div>
  );
}
