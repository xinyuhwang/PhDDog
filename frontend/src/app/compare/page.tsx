"use client";

import Link from "next/link";
import { Fragment, useState } from "react";

import { Badge, Card, ContactBadge, inputClass, RecruitingBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

type Faculty = {
  id: string; name: string; department: string | null; recruiting_status: string; recruiting_cycle: string | null;
  recruiting_confidence: string | null; recruiting_stale: boolean; contact_policy: string; pinned: boolean; in_program: boolean; note: string | null;
};
type Row = {
  id: string; school_id: string; school_name: string; program: string; program_type: string; deadline: string | null; days_left: number | null;
  status: string; fit_score: number | null; tier: string | null; reason: string | null; gaps: string | null; decision: string;
  assessment_by: string | null; faculty: Faculty[]; n_faculty: number; n_in_program: number; n_recruiting: number;
  n_target_cycle: number; n_not_recruiting: number;
};

const DECISIONS: Record<string, [string, string]> = {
  final5: ["Final 5", "bg-emerald-600 text-white"],
  top8: ["Top 8", "bg-indigo-600 text-white"],
  undecided: ["Undecided", "bg-stone-100 text-stone-700"],
  drop: ["Drop", "bg-stone-200 text-stone-500 line-through"],
};
const TIER_TONE: Record<string, "red" | "yellow" | "green"> = { reach: "red", target: "yellow", likely: "green" };

export default function ComparePage() {
  const { data: rows, reload, setData } = useApi<Row[]>("/compare");
  const [open, setOpen] = useState<string | null>(null);
  const [showDropped, setShowDropped] = useState(true);

  async function patch(id: string, body: Partial<Row>) {
    // Optimistic update so selects feel instant; the server marks the row as edited by you.
    setData((rs) => rs?.map((r) => (r.id === id ? { ...r, ...body, assessment_by: "user" } : r)));
    await api.patch(`/applications/${id}`, body);
    reload();
  }

  const count = (d: string) => rows?.filter((r) => r.decision === d).length ?? 0;
  const tiers = (d: string[]) => {
    const sel = rows?.filter((r) => d.includes(r.decision)) ?? [];
    return ["reach", "target", "likely"].map((t) => `${sel.filter((r) => r.tier === t).length} ${t}`).join(" · ");
  };
  const visible = rows?.filter((r) => showDropped || r.decision !== "drop") ?? [];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
          <div className="text-2xl font-semibold">{rows?.length ?? 0}</div>
          <div className="text-sm text-stone-500">programs at your {new Set(rows?.map((r) => r.school_id)).size} schools</div>
        </div>
        <div className={`rounded-lg border p-4 shadow-sm ${count("top8") + count("final5") > 8 ? "border-amber-300 bg-amber-50" : "border-stone-200 bg-white"}`}>
          <div className="text-2xl font-semibold">{count("top8") + count("final5")} <span className="text-base font-normal text-stone-500">/ 8</span></div>
          <div className="text-sm text-stone-500">Top 8 (incl. Final 5) · {tiers(["top8", "final5"])}</div>
        </div>
        <div className={`rounded-lg border p-4 shadow-sm ${count("final5") > 5 ? "border-amber-300 bg-amber-50" : "border-stone-200 bg-white"}`}>
          <div className="text-2xl font-semibold">{count("final5")} <span className="text-base font-normal text-stone-500">/ 5</span></div>
          <div className="text-sm text-stone-500">Final 5 · {tiers(["final5"])}</div>
        </div>
      </div>

      <Card title="Compare programs" actions={
        <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={showDropped} onChange={(e) => setShowDropped(e.target.checked)} /> Show dropped</label>
      }>
        <p className="mb-4 text-sm text-stone-600">
          Faculty and recruiting counts come from the app. Fit, tier, reasons and gaps were <b>suggested by Claude</b> from your resume and the
          evidence; change anything and it becomes yours. Aim for a mix, roughly 2 reach + 2 target + 1 likely.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-stone-500">
              <tr>
                <th className="py-2 pr-2">Decision</th><th className="pr-2">Program</th><th className="pr-2">Faculty</th>
                <th className="pr-2">Fit</th><th className="pr-2">Tier</th><th className="pr-2">Deadline</th><th />
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <Fragment key={r.id}>
                  <tr className={`border-t border-stone-100 align-top ${r.decision === "drop" ? "opacity-50" : ""}`}>
                    <td className="py-2 pr-2">
                      <select className={`rounded-md px-2 py-1 text-xs font-medium ${DECISIONS[r.decision][1]}`} value={r.decision}
                        onChange={(e) => patch(r.id, { decision: e.target.value })}>
                        {Object.entries(DECISIONS).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
                      </select>
                    </td>
                    <td className="pr-2">
                      <button className="text-left font-medium hover:text-indigo-700" onClick={() => setOpen(open === r.id ? null : r.id)}>
                        {r.school_name}<span className="block font-normal text-stone-600">{r.program}</span>
                      </button>
                      <div className="mt-1 flex flex-wrap gap-1">
                        <Badge>{r.program_type}</Badge>
                        {r.assessment_by === "claude" && <Badge tone="blue" title="Pre-filled by Claude — adjust freely">suggested</Badge>}
                      </div>
                    </td>
                    <td className="pr-2 text-xs">
                      <div><b>{r.n_faculty}</b> matched{r.n_in_program !== r.n_faculty ? ` (${r.n_in_program} likely in this program)` : ""}</div>
                      <div className={r.n_recruiting ? "text-emerald-700" : "text-stone-500"}>{r.n_recruiting} of those recruiting</div>
                      {r.n_target_cycle > 0 && <div className="font-medium text-emerald-700">{r.n_target_cycle} name Fall 2027</div>}
                      {r.n_not_recruiting > 0 && <div className="text-rose-700">{r.n_not_recruiting} not recruiting</div>}
                    </td>
                    <td className="pr-2">
                      <select className={`${inputClass} w-16 py-1`} value={r.fit_score ?? ""} onChange={(e) => patch(r.id, { fit_score: e.target.value ? Number(e.target.value) : null })}>
                        <option value="">–</option>{[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n}</option>)}
                      </select>
                    </td>
                    <td className="pr-2">
                      <select className={`${inputClass} w-24 py-1`} value={r.tier ?? ""} onChange={(e) => patch(r.id, { tier: e.target.value || null })}>
                        <option value="">–</option><option value="reach">Reach</option><option value="target">Target</option><option value="likely">Likely</option>
                      </select>
                      {r.tier && <div className="mt-1"><Badge tone={TIER_TONE[r.tier]}>{r.tier}</Badge></div>}
                    </td>
                    <td className="whitespace-nowrap pr-2 text-xs">
                      {r.deadline ? new Date(`${r.deadline}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—"}
                      {r.days_left !== null && <div className="text-stone-500">{r.days_left}d</div>}
                    </td>
                    <td><button className="text-xs text-indigo-600 hover:underline" onClick={() => setOpen(open === r.id ? null : r.id)}>{open === r.id ? "Hide" : "Details"}</button></td>
                  </tr>
                  {r.reason && open !== r.id && (
                    <tr className={r.decision === "drop" ? "opacity-50" : ""}><td /><td colSpan={6} className="pb-2 text-xs text-stone-600">{r.reason}</td></tr>
                  )}
                  {open === r.id && (
                    <tr><td colSpan={7} className="pb-4">
                      <div className="grid gap-4 rounded-md bg-stone-50 p-4 lg:grid-cols-2">
                        <div className="space-y-3">
                          <label className="block text-xs font-medium text-stone-700">Why apply (your coherent reason)
                            <textarea className={`${inputClass} mt-1 h-28 text-sm font-normal`} defaultValue={r.reason ?? ""}
                              onBlur={(e) => e.target.value !== (r.reason ?? "") && patch(r.id, { reason: e.target.value })} />
                          </label>
                          <label className="block text-xs font-medium text-stone-700">Gaps & risks
                            <textarea className={`${inputClass} mt-1 h-24 text-sm font-normal`} defaultValue={r.gaps ?? ""}
                              onBlur={(e) => e.target.value !== (r.gaps ?? "") && patch(r.id, { gaps: e.target.value })} />
                          </label>
                          <Link href="/applications" className="text-xs text-indigo-600 hover:underline">Open in Applications →</Link>
                        </div>
                        <div>
                          <div className="mb-2 text-xs font-medium text-stone-700">Matched faculty at {r.school_name}</div>
                          <ul className="space-y-2">
                            {r.faculty.map((f) => (
                              <li key={f.id} className="text-xs">
                                <div className="flex flex-wrap items-center gap-1">
                                  {f.pinned && <span title="Pinned">📌</span>}
                                  <Link href={`/professors/${f.id}`} className="font-medium text-indigo-600 hover:underline">{f.name}</Link>
                                  {!f.in_program && <Badge title="Department suggests a different program">other program?</Badge>}
                                  <RecruitingBadge status={f.recruiting_status} cycle={f.recruiting_cycle} stale={f.recruiting_stale} />
                                  {f.recruiting_confidence && <span className="text-stone-400">{f.recruiting_confidence}</span>}
                                  {f.contact_policy !== "unknown" && <ContactBadge policy={f.contact_policy} />}
                                </div>
                                {f.note && <div className="mt-0.5 text-stone-600">{f.note}</div>}
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
