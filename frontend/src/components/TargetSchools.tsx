"use client";

import Link from "next/link";
import { useState } from "react";

import { Button, Card, ErrorNote, inputClass } from "@/components/ui";
import { api, type School } from "@/lib/api";
import { useApi } from "@/lib/hooks";

/** Pick the schools you're applying to. Chosen schools get an Applications tracker card. */
export default function TargetSchools() {
  const { data: schools, reload } = useApi<School[]>("/schools");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function toggle(s: School) {
    await api.patch(`/schools/${s.id}/target`, { is_target: !s.is_target });
    reload();
  }

  async function add() {
    setError(null);
    try {
      const s = await api.post<School>("/schools", { name, is_target: true });
      setName("");
      reload();
      if (!s.confirmed) setError(`"${s.name}" wasn't recognized — confirm it on the Add professors page.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const targets = schools?.filter((s) => s.is_target) ?? [];
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
          </button>
        ))}
        {schools && !schools.length && <span className="text-sm text-stone-400">No schools yet.</span>}
      </div>
      <div className="mt-4 flex gap-2">
        <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} placeholder="Add a school, e.g. UCLA or Columbia University"
          onKeyDown={(e) => e.key === "Enter" && name.trim() && add()} />
        <Button disabled={!name.trim()} onClick={add}>Add</Button>
      </div>
      <div className="mt-2"><ErrorNote error={error} /></div>
    </Card>
  );
}
