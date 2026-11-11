"use client";

import Link from "next/link";
import { useState } from "react";

import { Button, Card, ErrorNote, inputClass } from "@/components/ui";
import { api, type School } from "@/lib/api";
import { useApi } from "@/lib/hooks";

/** Pick the schools you're applying to. Chosen schools get an Applications tracker card. */
export default function TargetSchools({ onChange }: { onChange?: () => void }) {
  const { data: schools, reload } = useApi<School[]>("/schools");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function toggle(s: School) {
    await api.patch(`/schools/${s.id}/target`, { is_target: !s.is_target });
    reload();
    onChange?.();
  }

  async function add() {
    setError(null);
    try {
      const s = await api.post<School>("/schools", { name, is_target: true });
      setName("");
      reload();
      onChange?.();
      if (!s.confirmed) setError(`"${s.name}" wasn't recognized — confirm it on the Add professors page.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const targets = schools?.filter((s) => s.is_target) ?? [];
  const guaranteed = (schools ?? []).filter((s) => s.funding_guarantee)
    .sort((a, b) => Number(b.is_target) - Number(a.is_target) || a.name.localeCompare(b.name));
  const flagged = (schools ?? []).filter((s) => s.funding_level === "concern" || s.funding_level === "minor")
    .sort((a, b) => Number(b.is_target) - Number(a.is_target) || Number(b.funding_level === "concern") - Number(a.funding_level === "concern"));
  return (
    <Card title={`Schools I'm applying to (${targets.length})`}
      actions={<Link href="/applications" className="text-sm text-indigo-600 hover:underline">Applications →</Link>}>
      <p className="mb-3 text-sm text-stone-600">Click to select or unselect. Selected schools appear on your Applications page.</p>
      <div className="flex flex-wrap gap-2">
        {schools?.map((s) => (
          <button key={s.id} onClick={() => toggle(s)} aria-pressed={s.is_target}
            className={`rounded-full px-3 py-1 text-sm ring-1 ring-inset transition ${s.is_target
              ? "bg-indigo-600 text-white ring-indigo-600 hover:bg-indigo-700"
              : "bg-white text-stone-600 ring-stone-300 hover:bg-stone-50"}`}>
            {s.is_target ? "✓ " : ""}{s.name}
            {s.professor_count > 0 && <span className={s.is_target ? "text-indigo-200" : "text-stone-400"}> · {s.professor_count}</span>}
            {s.funding_guarantee && (
              <span title={`Funding guaranteed: ${s.funding_guarantee}`}
                className={`ml-1.5 rounded px-1 text-xs font-semibold ${s.is_target ? "bg-emerald-300 text-emerald-950" : "bg-emerald-100 text-emerald-800"}`}>✓ funded</span>
            )}
            <FundingMark level={s.funding_level} onDark={s.is_target} />
          </button>
        ))}
        {schools && !schools.length && <span className="text-sm text-stone-400">No schools yet.</span>}
      </div>
      {guaranteed.length > 0 && (
        <details className="mt-4 rounded-md border border-emerald-200 bg-emerald-50/60 p-3 text-sm">
          <summary className="cursor-pointer font-medium text-emerald-900">Funding guaranteed: {guaranteed.length} schools</summary>
          <ul className="mt-2 space-y-2">
            {guaranteed.map((s) => (
              <li key={s.id}>
                <span className="font-medium text-stone-800">✓ {s.name}</span>
                {!s.is_target && <span className="text-stone-500"> (not selected)</span>}
                <p className="whitespace-pre-wrap text-stone-600">{s.funding_guarantee}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
      {flagged.length > 0 && (
        <details className="mt-4 rounded-md border border-amber-200 bg-amber-50/60 p-3 text-sm" open={flagged.some((s) => s.is_target && s.funding_level === "concern")}>
          <summary className="cursor-pointer font-medium text-amber-900">
            Funding concerns: {flagged.filter((s) => s.funding_level === "concern").length} schools · {flagged.filter((s) => s.funding_level === "minor").length} minor
          </summary>
          <ul className="mt-2 space-y-2">
            {flagged.map((s) => (
              <li key={s.id}>
                <span className="font-medium text-stone-800">{s.funding_level === "concern" ? "⚠ " : "ⓘ "}{s.name}</span>
                {!s.is_target && <span className="text-stone-500"> (not selected)</span>}
                <p className="whitespace-pre-wrap text-stone-600">{s.funding_note}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="mt-4 flex gap-2">
        <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} placeholder="Add a school, e.g. UCLA or Columbia University"
          onKeyDown={(e) => e.key === "Enter" && name.trim() && add()} />
        <Button disabled={!name.trim()} onClick={add}>Add</Button>
      </div>
      <div className="mt-2"><ErrorNote error={error} /></div>
    </Card>
  );
}

/** ⚠ for an evidence-based funding concern, ⓘ for minor (budget pressure, PhD funding protected). */
function FundingMark({ level, onDark }: { level: School["funding_level"]; onDark: boolean }) {
  if (level === "concern")
    return <span title="Funding concern: see details below" className={`ml-1.5 rounded px-1 text-xs font-semibold ${onDark ? "bg-amber-300 text-amber-950" : "bg-amber-100 text-amber-900"}`}>⚠ funding</span>;
  if (level === "minor")
    return <span title="Minor: university budget pressure, PhD funding protected" className={`ml-1.5 text-xs ${onDark ? "text-indigo-200" : "text-stone-400"}`}>ⓘ</span>;
  return null;
}
