"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge, Button, Card, ErrorNote, inputClass, ResolveBadge } from "@/components/ui";
import { api, type ParsedEntry, type ProfessorSummary } from "@/lib/api";
import { useApi } from "@/lib/hooks";

type School = { id: string; name: string; aliases: string[]; primary_domain: string | null; confirmed: boolean };

const EXAMPLE = `Jacob Gardner (UPenn CIS)
Mark Yatskar, UPenn
Eric Eaton - University of Pennsylvania, Computer Science
Pranam Chatterjee UPenn Bioengineering https://www.chatterjeelab.com/`;

const ISSUE_TEXT: Record<string, string> = {
  missing_school: "No school — add one",
  unclear_name: "Name unclear",
  duplicate: "Already added",
};

export default function AddPage() {
  const [text, setText] = useState("");
  const [entries, setEntries] = useState<ParsedEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const profs = useApi<ProfessorSummary[]>("/professors", (d) => d.some((p) => p.resolve_status === "pending"));
  const schools = useApi<School[]>("/schools");

  async function preview() {
    setError(null);
    try {
      setEntries(await api.post<ParsedEntry[]>("/professors/parse", { text }));
    } catch (e) {
      setError(String(e));
    }
  }

  function edit(i: number, field: keyof ParsedEntry, value: string) {
    setEntries((es) => es!.map((e, j) => {
      if (j !== i) return e;
      const next = { ...e, [field]: value || null };
      // Editing clears the issue it fixes; duplicates stay flagged.
      next.issues = e.issues.filter((iss) => !((iss === "missing_school" && next.school_raw) || (iss === "unclear_name" && next.name)));
      return next;
    }));
  }

  async function add() {
    setBusy(true);
    try {
      await api.post("/professors/bulk", { entries });
      setEntries(null);
      setText("");
      await Promise.all([profs.reload(), schools.reload()]);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const addable = entries?.filter((e) => e.name && e.school_raw && !e.issues.includes("duplicate")).length ?? 0;
  const attention = profs.data?.filter((p) => p.resolve_status !== "resolved") ?? [];
  const unconfirmed = schools.data?.filter((s) => !s.confirmed) ?? [];

  return (
    <div className="space-y-6">
      <Card title="Add professors">
        <p className="mb-2 text-sm text-stone-600">
          One professor per line (or separate with <code>;</code>). Each needs a <b>name</b> and a <b>school</b>; department and homepage URL are optional.
          A line like <code>UPenn:</code> sets the school for the lines below it.
        </p>
        <textarea className={`${inputClass} h-36 font-mono`} value={text} onChange={(e) => setText(e.target.value)} placeholder={EXAMPLE} />
        <div className="mt-3 flex gap-2">
          <Button onClick={preview} disabled={!text.trim()}>Preview</Button>
          {!text && <Button variant="secondary" onClick={() => setText(EXAMPLE)}>Use example</Button>}
        </div>
        <div className="mt-3"><ErrorNote error={error} /></div>

        {entries && (
          <div className="mt-5">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-stone-500">
                  <tr><th className="py-2 pr-2">Name</th><th className="pr-2">School</th><th className="pr-2">Department</th><th className="pr-2">URL</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {entries.map((e, i) => (
                    <tr key={i} className="border-t border-stone-100 align-top">
                      {(["name", "school_raw", "department_raw", "url"] as const).map((f) => (
                        <td key={f} className="py-2 pr-2">
                          <input className={`${inputClass} py-1`} value={e[f] ?? ""} onChange={(ev) => edit(i, f, ev.target.value)} />
                        </td>
                      ))}
                      <td className="py-2">
                        {e.issues.length ? e.issues.map((iss) => <Badge key={iss} tone={iss === "duplicate" ? "gray" : "red"}>{ISSUE_TEXT[iss] ?? iss}</Badge>) : <Badge tone="green">Ready</Badge>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-center gap-3">
              <Button onClick={add} disabled={busy || addable === 0}>Add {addable} professor{addable === 1 ? "" : "s"}</Button>
              <span className="text-xs text-stone-500">Entries with issues are skipped. The app then finds each homepage and reads it.</span>
            </div>
          </div>
        )}
      </Card>

      {unconfirmed.length > 0 && (
        <Card title="Confirm new schools">
          <p className="mb-3 text-sm text-stone-600">These schools weren&apos;t recognized. Add the web domain (e.g. <code>mit.edu</code>) so the app can check homepages belong to the right school.</p>
          {unconfirmed.map((s) => <SchoolRow key={s.id} school={s} onSaved={schools.reload} />)}
        </Card>
      )}

      <Card title="Needs attention" actions={<Link href="/professors" className="text-sm text-indigo-600 hover:underline">All professors →</Link>}>
        {!attention.length ? <p className="text-sm text-stone-500">Everyone added so far was found.</p> : (
          <ul className="divide-y divide-stone-100">
            {attention.map((p) => <AttentionRow key={p.id} prof={p} onSaved={profs.reload} />)}
          </ul>
        )}
      </Card>
    </div>
  );
}

function SchoolRow({ school, onSaved }: { school: School; onSaved: () => void }) {
  const [domain, setDomain] = useState(school.primary_domain ?? "");
  return (
    <div className="flex flex-wrap items-center gap-2 py-1 text-sm">
      <span className="w-64 font-medium">{school.name}</span>
      <input className={`${inputClass} w-48 py-1`} value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="school.edu" />
      <Button variant="secondary" onClick={async () => { await api.patch(`/schools/${school.id}`, { primary_domain: domain || null, confirmed: true }); onSaved(); }}>Confirm</Button>
    </div>
  );
}

function AttentionRow({ prof, onSaved }: { prof: ProfessorSummary; onSaved: () => void }) {
  const [url, setUrl] = useState("");
  return (
    <li className="flex flex-wrap items-center gap-3 py-3 text-sm">
      <Link href={`/professors/${prof.id}`} className="w-48 font-medium hover:text-indigo-700">{prof.name}</Link>
      <span className="w-48 text-stone-500">{prof.school_name}</span>
      <ResolveBadge status={prof.resolve_status} />
      {prof.resolve_status !== "pending" && (
        <>
          <span className="text-stone-500">{prof.resolve_error}</span>
          <input className={`${inputClass} w-72 py-1`} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://… homepage URL" />
          <Button variant="secondary" disabled={!url} onClick={async () => { await api.post(`/professors/${prof.id}/homepage`, { url }); setUrl(""); onSaved(); }}>Use this URL</Button>
        </>
      )}
    </li>
  );
}
