"use client";

import Link from "next/link";
import { Fragment, useMemo, useState } from "react";

import { Button, Card, ContactBadge, ErrorNote, FitBadge, PinButton, RecruitingBadge, ResolveBadge, StageBadge, inputClass } from "@/components/ui";
import { api, type Job, type ProfessorSummary, type Profile } from "@/lib/api";
import { useApi, useShowFit } from "@/lib/hooks";

const FIT_ORDER: Record<string, number> = { strong: 0, possible: 1, no: 2 };
const RECRUIT_ORDER: Record<string, number> = { explicitly_recruiting: 0, recruits_generally: 1, unknown: 2, not_recruiting: 3 };
type SortKey = "fit" | "recruiting" | "name" | "school";
// Group order on the page, before the chosen sort: pinned with papers analyzed (or later) → pinned → others.
// Unpinning keeps the stage but moves the professor to "Others".
const GROUPS = ["Papers analyzed", "Pinned", "Others", "Dismissed"];
const ANALYZED_OR_LATER = ["analyzed", "drafted", "contacted", "replied"];
const groupOf = (p: ProfessorSummary) =>
  p.status === "dismissed" ? 3 : !p.pinned ? 2 : ANALYZED_OR_LATER.includes(p.status) ? 0 : 1;
// Match notes that call out an especially close fit rank first within each group.
const STRONG_MATCH = /\b(closest|direct (match|overlap)|strongest|very strong|best (overall )?(\w+ )?match)\b/i;
const strongMatch = (p: ProfessorSummary) => !!p.notes && STRONG_MATCH.test(p.notes);

export default function ProfessorsPage() {
  const jobs = useApi<Job[]>("/jobs", (d) => d.some((j) => j.status !== "failed"));
  const profs = useApi<ProfessorSummary[]>(
    "/professors", (d) => d.some((p) => p.resolve_status === "pending") || !!jobs.data?.some((j) => j.status !== "failed"),
  );
  const [sort, setSort] = useState<SortKey>("fit");
  const [school, setSchool] = useState("");
  const [hideDismissed, setHideDismissed] = useState(true);
  const [query, setQuery] = useState("");
  const [screenError, setScreenError] = useState<string | null>(null);
  const { data: profile } = useApi<Profile | null>("/profile");
  const showFit = useShowFit();
  const sortBy: SortKey = !showFit && sort === "fit" ? "recruiting" : sort;

  const rows = useMemo(() => {
    let list = profs.data ?? [];
    if (school) list = list.filter((p) => p.school_name === school);
    if (hideDismissed) list = list.filter((p) => p.status !== "dismissed");
    if (query) list = list.filter((p) => `${p.name} ${p.department ?? ""} ${p.notes ?? ""}`.toLowerCase().includes(query.toLowerCase()));
    const key = (p: ProfessorSummary) => [groupOf(p), strongMatch(p) ? 0 : 1, ...({
      fit: [FIT_ORDER[p.screen?.label ?? ""] ?? 3, -(p.screen?.score ?? 0)],
      recruiting: [RECRUIT_ORDER[p.recruiting_status] ?? 2, p.recruiting_stale ? 1 : 0],
      name: [p.name],
      school: [p.school_name, p.name],
    })[sortBy]];
    return [...list].sort((a, b) => {
      const [ka, kb] = [key(a), key(b)];
      for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return ka[i] < kb[i] ? -1 : 1;
      return 0;
    });
  }, [profs.data, sortBy, school, hideDismissed, query]);

  const schools = [...new Set(profs.data?.map((p) => p.school_name))].sort();
  const screening = jobs.data?.some((j) => j.kind === "screen_all" && j.status !== "failed");

  async function togglePin(p: ProfessorSummary) {
    await api.patch(`/professors/${p.id}`, { pinned: !p.pinned });
    profs.reload();
  }

  return (
    <Card
      title={`Professors (${rows.length})`}
      actions={showFit && <Button variant="secondary" disabled={screening || profile === null} onClick={async () => {
        setScreenError(null);
        try { await api.post("/professors/screen"); jobs.reload(); } catch (e) { setScreenError(e instanceof Error ? e.message : String(e)); }
      }}>{screening ? "Screening…" : "Re-run screening"}</Button>}
    >
      {showFit && profile === null && (
        <p className="mb-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Research fit needs your profile. <Link href="/profile" className="font-medium underline">Upload your resume or add a research statement</Link> — screening then runs automatically.
        </p>
      )}
      <div className="mb-4 empty:hidden"><ErrorNote error={screenError} /></div>
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <input className={`${inputClass} w-56 py-1`} placeholder="Search name, dept, notes" value={query} onChange={(e) => setQuery(e.target.value)} />
        <select className={`${inputClass} w-64 py-1`} value={school} onChange={(e) => setSchool(e.target.value)}>
          <option value="">All schools</option>
          {schools.map((s) => <option key={s}>{s}</option>)}
        </select>
        <label className="flex items-center gap-1">Sort
          <select className={`${inputClass} w-40 py-1`} value={sortBy} onChange={(e) => setSort(e.target.value as SortKey)}>
            {showFit && <option value="fit">Research fit</option>}<option value="recruiting">Recruiting</option>
            <option value="name">Name</option><option value="school">School</option>
          </select>
        </label>
        <label className="flex items-center gap-1"><input type="checkbox" checked={hideDismissed} onChange={(e) => setHideDismissed(e.target.checked)} /> Hide dismissed</label>
      </div>

      {!profs.data?.length ? (
        <p className="text-sm text-stone-500">No professors yet. <Link href="/add" className="text-indigo-600 hover:underline">Add some →</Link></p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-stone-500">
              <tr><th className="py-2">Professor</th>{showFit && <th>Research fit</th>}<th>Recruiting</th><th>Contact</th><th title="Where they are in your outreach">Stage</th><th /></tr>
            </thead>
            <tbody>
              {rows.map((p, i) => (
                <Fragment key={p.id}>
                {(i === 0 || groupOf(rows[i - 1]) !== groupOf(p)) && (
                  <tr className="border-t border-stone-200 bg-stone-50">
                    <td colSpan={showFit ? 6 : 5} className="px-1 py-1.5 text-xs font-semibold uppercase tracking-wide text-stone-500">
                      {GROUPS[groupOf(p)]} ({rows.filter((r) => groupOf(r) === groupOf(p)).length})
                    </td>
                  </tr>
                )}
                <tr className={`border-t border-stone-100 align-top ${p.status === "dismissed" ? "opacity-50" : ""}`}>
                  <td className="py-2.5 pr-3">
                    <Link href={`/professors/${p.id}`} className="font-medium text-stone-900 hover:text-indigo-700">{p.name}</Link>
                    <div className="text-xs text-stone-500">{[p.title, p.department, p.school_name].filter(Boolean).join(" · ")}</div>
                    {p.notes && (
                      <div className={`mt-1 max-w-md text-xs ${strongMatch(p) ? "font-medium text-indigo-800" : "text-stone-600"}`}>
                        {strongMatch(p) && <span title="Especially close match">★ </span>}
                        {p.notes.replace(/^Why it matches \(from search\): /, "")}
                      </div>
                    )}
                    {p.resolve_status !== "resolved" && <div className="mt-1"><ResolveBadge status={p.resolve_status} /></div>}
                  </td>
                  {showFit && (
                    <td className="pr-3">
                      <FitBadge label={p.screen?.label} reason={p.screen?.reason} />
                      {p.screen && <div className="mt-1 max-w-56 text-xs text-stone-500">{p.screen.reason}</div>}
                    </td>
                  )}
                  <td className="pr-3">
                    <RecruitingBadge status={p.recruiting_status} cycle={p.recruiting_cycle} stale={p.recruiting_stale} />
                    {p.recruiting_confidence && <div className="mt-1 text-xs text-stone-500">{p.recruiting_confidence} confidence</div>}
                    {p.check_stale && <div className="mt-1 text-xs text-amber-700" title="Last site check is old">⚠ checked {new Date(p.last_checked_at!).toLocaleDateString()}</div>}
                  </td>
                  <td className="pr-3"><ContactBadge policy={p.contact_policy} /></td>
                  <td className="pr-3"><StageBadge status={p.status} /></td>
                  <td className="whitespace-nowrap">
                    <div className="flex items-center gap-3">
                      {p.status !== "dismissed" && (
                        <>
                          <PinButton pinned={p.pinned} onClick={() => togglePin(p)} />
                          <Link href={`/professors/${p.id}#papers`} title="Add a paper"
                            className="rounded-md px-2 py-0.5 text-sm font-medium text-indigo-600 ring-1 ring-inset ring-indigo-200 hover:bg-indigo-50">
                            + paper
                          </Link>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
