"use client";

import { useState } from "react";

import { Badge, Button, Card, ErrorNote, inputClass } from "@/components/ui";
import { api, type Venue } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const STATUSES: Venue["status"][] = ["considering", "target", "submitted", "accepted", "rejected", "dropped"];
const STATUS_TONE: Record<Venue["status"], "gray" | "blue" | "yellow" | "green" | "red"> = {
  considering: "gray", target: "blue", submitted: "yellow", accepted: "green", rejected: "red", dropped: "gray",
};
const fmt = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
const daysUntil = (d: string) => Math.round((new Date(`${d}T12:00:00`).getTime() - Date.now()) / 86_400_000);

function Deadline({ v }: { v: Venue }) {
  if (!v.deadline) return <span className="text-sm text-stone-500">{v.deadline_text ?? "No deadline"}</span>;
  const n = daysUntil(v.deadline);
  return (
    <span className="flex flex-wrap items-center gap-2 text-sm">
      <span className="font-medium text-stone-800">{fmt(v.deadline)}</span>
      {n < 0 ? <Badge>passed</Badge> : <Badge tone={n <= 30 ? "red" : n <= 90 ? "yellow" : "gray"}>in {n}d</Badge>}
      {v.deadline_text && <span className="text-stone-500">{v.deadline_text}</span>}
    </span>
  );
}

export default function PublishingPage() {
  const venues = useApi<Venue[]>("/venues");
  const [adding, setAdding] = useState(false);
  const active = venues.data?.filter((v) => v.status !== "dropped") ?? [];
  const dropped = venues.data?.filter((v) => v.status === "dropped") ?? [];

  return (
    <div className="space-y-6">
      <Card title="Publishing targets"
        actions={<Button variant="secondary" onClick={() => setAdding(!adding)}>{adding ? "Close" : "+ Add venue"}</Button>}>
        <p className="mb-4 max-w-3xl text-sm text-stone-600">
          Where to submit your liver tumor paper, ranked from the top. Each entry says why it fits, both for the work and for
          the groups you&apos;re applying to. Change a venue&apos;s status as plans firm up.
        </p>
        {adding && <VenueForm nextRank={(venues.data?.length ?? 0) + 1} onSaved={() => { setAdding(false); venues.reload(); }} />}
        {venues.data && !venues.data.length && !adding && <p className="text-sm text-stone-500">No venues yet. Add one to start.</p>}
        <ol className="space-y-3">
          {active.map((v) => <VenueCard key={v.id} venue={v} onChanged={venues.reload} />)}
        </ol>
      </Card>
      {dropped.length > 0 && (
        <Card title={`Dropped (${dropped.length})`}>
          <ol className="space-y-3 opacity-70">{dropped.map((v) => <VenueCard key={v.id} venue={v} onChanged={venues.reload} />)}</ol>
        </Card>
      )}
    </div>
  );
}

function VenueCard({ venue: v, onChanged }: { venue: Venue; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const patch = async (body: Partial<Venue>) => { await api.patch(`/venues/${v.id}`, body); onChanged(); };
  if (editing) return <li className="rounded-md border border-stone-200 p-4"><VenueForm venue={v} onSaved={() => { setEditing(false); onChanged(); }} onCancel={() => setEditing(false)} /></li>;
  return (
    <li className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-3 rounded-md border border-stone-200 p-4">
      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-50 text-sm font-semibold text-indigo-700">{v.rank}</span>
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-base font-semibold text-stone-900">{v.name}</span>
          <Badge>{v.kind}</Badge>
          {v.tier && <Badge tone="blue">{v.tier}</Badge>}
          <span className="ml-auto flex items-center gap-2">
            <select aria-label="Status" className={`${inputClass} w-36 py-1 text-xs`} value={v.status} onChange={(e) => patch({ status: e.target.value as Venue["status"] })}>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <Badge tone={STATUS_TONE[v.status]}>{v.status}</Badge>
          </span>
        </div>
        <Deadline v={v} />
        {v.why && <p className="whitespace-pre-wrap text-sm text-stone-700">{v.why}</p>}
        {v.notes && <p className="whitespace-pre-wrap rounded-md bg-amber-50/70 px-3 py-2 text-sm text-stone-700">{v.notes}</p>}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          {v.links.map((l, i) => <a key={i} href={l.url} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">{l.label} ↗</a>)}
          <span className="ml-auto flex gap-1">
            <Button variant="secondary" onClick={() => setEditing(true)}>Edit</Button>
            <Button variant="danger" onClick={async () => { if (confirm(`Delete ${v.name}?`)) { await api.del(`/venues/${v.id}`); onChanged(); } }}>Delete</Button>
          </span>
        </div>
      </div>
    </li>
  );
}

/** Links: one per line as "Label | URL". */
function VenueForm({ venue, nextRank, onSaved, onCancel }: { venue?: Venue; nextRank?: number; onSaved: () => void; onCancel?: () => void }) {
  const [f, setF] = useState({
    name: venue?.name ?? "", rank: String(venue?.rank ?? nextRank ?? 1), kind: venue?.kind ?? "conference", tier: venue?.tier ?? "",
    deadline: venue?.deadline ?? "", deadline_text: venue?.deadline_text ?? "", why: venue?.why ?? "", notes: venue?.notes ?? "",
    links: venue?.links.map((l) => `${l.label} | ${l.url}`).join("\n") ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  async function save() {
    const body = {
      name: f.name.trim(), rank: Number(f.rank) || 0, kind: f.kind, tier: f.tier.trim() || null,
      deadline: f.deadline || null, deadline_text: f.deadline_text.trim() || null, why: f.why.trim() || null, notes: f.notes.trim() || null,
      links: f.links.split("\n").map((x) => x.trim()).filter(Boolean).map((line) => {
        const [label, url] = line.includes("|") ? line.split("|").map((x) => x.trim()) : [line, line];
        return { label: label || url, url };
      }),
    };
    try {
      await (venue ? api.patch(`/venues/${venue.id}`, body) : api.post("/venues", body));
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="mb-4 space-y-2 text-sm">
      <div className="flex flex-wrap gap-2">
        <input aria-label="Rank" type="number" min={0} className={`${inputClass} w-20`} value={f.rank} onChange={set("rank")} />
        <input aria-label="Venue name" className={`${inputClass} min-w-0 flex-1`} value={f.name} onChange={set("name")} placeholder="Venue, e.g. MICCAI 2027" />
        <select aria-label="Type" className={`${inputClass} w-36`} value={f.kind} onChange={set("kind")}>
          <option value="conference">conference</option><option value="journal">journal</option><option value="workshop">workshop</option>
        </select>
        <input aria-label="Tier" className={`${inputClass} w-40`} value={f.tier} onChange={set("tier")} placeholder="Tier, e.g. top" />
      </div>
      <div className="flex flex-wrap gap-2">
        <input aria-label="Deadline" type="date" className={`${inputClass} w-44`} value={f.deadline} onChange={set("deadline")} />
        <input aria-label="Deadline note" className={`${inputClass} min-w-0 flex-1`} value={f.deadline_text} onChange={set("deadline_text")} placeholder="Deadline note, e.g. expected ~Mar 2027 or rolling" />
      </div>
      <textarea aria-label="Why it fits" className={`${inputClass} h-24`} value={f.why} onChange={set("why")} placeholder="Why it fits" />
      <textarea aria-label="Notes" className={`${inputClass} h-16`} value={f.notes} onChange={set("notes")} placeholder="Notes: page limits, review policy, preprint rules" />
      <textarea aria-label="Links" className={`${inputClass} h-16`} value={f.links} onChange={set("links")} placeholder="Links, one per line: Label | https://…" />
      <div className="flex gap-2">
        <Button disabled={!f.name.trim()} onClick={save}>{venue ? "Save" : "Add venue"}</Button>
        {onCancel && <Button variant="secondary" onClick={onCancel}>Cancel</Button>}
      </div>
      <ErrorNote error={error} />
    </div>
  );
}
