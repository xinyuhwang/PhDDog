"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Button, Card, ContactBadge, ErrorNote, FitBadge, PinButton, RecruitingBadge, ResolveBadge, StageBadge, inputClass } from "@/components/ui";
import { api, type Job, type ProfessorSummary, type Profile } from "@/lib/api";
import { useApi, useShowFit } from "@/lib/hooks";

const FIT_ORDER: Record<string, number> = { strong: 0, possible: 1, no: 2 };
const RECRUIT_ORDER: Record<string, number> = { explicitly_recruiting: 0, recruits_generally: 1, unknown: 2, not_recruiting: 3 };
type SortKey = "fit" | "recruiting" | "name" | "school";
// Later stages (analyzed, drafted, contacted…) already imply shortlisted.
const EARLY_STAGES = ["added", "resolved", "screened", "shortlisted"];

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
    if (query) list = list.filter((p) => `${p.name} ${p.department ?? ""}`.toLowerCase().includes(query.toLowerCase()));
    const key = (p: ProfessorSummary) => ({
      fit: [FIT_ORDER[p.screen?.label ?? ""] ?? 3, -(p.screen?.score ?? 0)],
      recruiting: [RECRUIT_ORDER[p.recruiting_status] ?? 2, p.recruiting_stale ? 1 : 0],
      name: [p.name],
      school: [p.school_name, p.name],
    })[sortBy];
    return [...list].sort((a, b) => {
      const [ka, kb] = [key(a), key(b)];
      for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return ka[i] < kb[i] ? -1 : 1;
      return 0;
    });
  }, [profs.data, sortBy, school, hideDismissed, query]);

  const schools = [...new Set(profs.data?.map((p) => p.school_name))].sort();
  const screening = jobs.data?.some((j) => j.kind === "screen_all" && j.status !== "failed");

  async function toggleShortlist(p: ProfessorSummary) {
    await api.patch(`/professors/${p.id}`, { status: p.status === "shortlisted" ? "screened" : "shortlisted" });
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
        <input className={`${inputClass} w-56 py-1`} placeholder="Search name / dept" value={query} onChange={(e) => setQuery(e.target.value)} />
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
              {rows.map((p) => (
                <tr key={p.id} className={`border-t border-stone-100 align-top ${p.status === "dismissed" ? "opacity-50" : ""}`}>
                  <td className="py-2.5 pr-3">
                    <Link href={`/professors/${p.id}`} className="font-medium text-stone-900 hover:text-indigo-700">{p.name}</Link>
                    <div className="text-xs text-stone-500">{[p.title, p.department, p.school_name].filter(Boolean).join(" · ")}</div>
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
                      {EARLY_STAGES.includes(p.status) && (
                        <PinButton pinned={p.status === "shortlisted"} onClick={() => toggleShortlist(p)} />
                      )}
                      {p.status !== "dismissed" && (
                        <Link href={`/professors/${p.id}#papers`} className="text-sm font-medium text-indigo-600 hover:underline">
                          {["shortlisted", "added", "resolved", "screened"].includes(p.status) ? "Add papers →" : "Open →"}
                        </Link>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
