"use client";

import { useState } from "react";

import { Badge, Button, Card, ErrorNote } from "@/components/ui";
import { api, type AdmissionRating, type AssessmentReason, type AssessmentRow, type Assessments, type Job } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const RATINGS: Record<AdmissionRating, ["green" | "blue" | "yellow" | "red", string, string]> = {
  likely: ["green", "Likely", "Your profile is at or above what recent admits show"],
  target: ["blue", "Target", "Your profile matches recent admits"],
  reach: ["yellow", "Reach", "Recent admits usually show more than your profile does now"],
  long_shot: ["red", "Long shot", "Very selective, and recent admits are well ahead of your profile"],
};
const ORDER: AdmissionRating[] = ["long_shot", "reach", "target", "likely"];

const KINDS: Record<AssessmentReason["kind"], string> = {
  profile: "Your materials",
  program: "Program page",
  faculty: "Faculty",
  admit_pattern: "Recent admits",
  funding: "Funding",
};

/** Chances at each selected program, with the evidence behind each reason (docs/DESIGN.md §4.11). */
export default function AdmissionChances() {
  const { data, reload } = useApi<Assessments>("/assessments");
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setError(null);
    setWaiting(true);
    try {
      await api.post("/assessments/run");
      // Wait for the background job to finish (or fail), up to about two minutes.
      for (let i = 0; i < 60; i++) {
        await new Promise((done) => setTimeout(done, 2000));
        const job = (await api.get<Job[]>("/jobs")).find((j) => j.kind === "assess_admission");
        if (!job) break;
        if (job.status === "failed") { setError(job.error?.split("\n")[0] ?? "Evaluation failed"); break; }
      }
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setWaiting(false);
    }
  }

  if (!data) return null;
  const rated = data.rows.filter((r) => r.rating);
  const counts = ORDER.map((k) => [k, rated.filter((r) => r.rating === k).length] as const);
  const noSafety = rated.length > 0 && !rated.some((r) => r.rating === "likely");
  const anyStale = rated.some((r) => r.stale.length);

  return (
    <Card title="Admission chances"
      actions={<Button disabled={!data.can_run || !data.has_profile || !data.rows.length || waiting} onClick={run}>
        {waiting ? "Evaluating…" : rated.length ? "Re-evaluate" : "Evaluate my chances"}
      </Button>}>
      <p className="mb-3 text-sm text-stone-600">
        A rough read of each selected program, from your resume and materials, the program&apos;s requirements, its faculty,
        funding, and what recent admits looked like. Ratings are categories, not percentages: there&apos;s no reliable admit data
        to support a number.
      </p>
      {!data.can_run && (
        <p className="mb-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Needs Claude: offline rules can&apos;t judge admission chances, so this app won&apos;t guess. Evaluations written by Claude
          in a session can still be imported and are shown below.
        </p>
      )}
      {!data.has_profile && <p className="mb-3 text-sm text-stone-500">Upload a resume first.</p>}
      {!data.rows.length && <p className="text-sm text-stone-500">Select the schools you&apos;re applying to above.</p>}
      <ErrorNote error={error} />

      {rated.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
          {counts.map(([k, n]) => <Badge key={k} tone={RATINGS[k][0]}>{RATINGS[k][1]}: {n}</Badge>)}
          {rated.length < data.rows.length && <Badge>Not evaluated: {data.rows.length - rated.length}</Badge>}
        </div>
      )}
      {noSafety && (
        <p className="mb-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
          No program is rated Likely. Consider adding one or two schools where you&apos;d be a stronger candidate.
        </p>
      )}
      {anyStale && (
        <p className="mb-3 text-sm text-amber-800">Some evaluations are out of date. Re-evaluate to refresh them.</p>
      )}

      <div className="space-y-3">
        {[...data.rows].sort(byRating).map((r) => <ProgramCard key={`${r.school_id}-${r.application_id}`} row={r} />)}
      </div>
    </Card>
  );
}

function byRating(a: AssessmentRow, b: AssessmentRow) {
  const rank = (r: AssessmentRow) => (r.rating ? ORDER.indexOf(r.rating) : -1);
  return rank(b) - rank(a) || a.school_name.localeCompare(b.school_name);
}

function ProgramCard({ row }: { row: AssessmentRow }) {
  const by = row.assessed_by === "claude-session" ? "Claude (session)" : row.assessed_by === "claude" ? "Claude" : row.assessed_by;
  return (
    <div className="rounded-md border border-stone-200 p-4">
      <div className="flex flex-wrap items-center gap-2">
        {row.rating
          ? <Badge tone={RATINGS[row.rating][0]} title={RATINGS[row.rating][2]}>{RATINGS[row.rating][1]}</Badge>
          : <Badge>Not evaluated</Badge>}
        <span className="font-medium text-stone-900">{row.school_name}</span>
        {row.program && <span className="text-sm text-stone-500">· {row.program}</span>}
        {row.stale.length > 0 && <Badge tone="yellow" title={row.stale.join("; ")}>Out of date</Badge>}
      </div>
      {row.rating && (
        <>
          {row.summary && <p className="mt-2 text-sm text-stone-700">{row.summary}</p>}
          <ul className="mt-2 space-y-2">
            {row.reasons.map((x, i) => (
              <li key={i} className="text-sm">
                <span className="text-stone-800">{x.text}</span>
                <div className="mt-0.5 flex flex-wrap items-baseline gap-2 text-xs text-stone-500">
                  <Badge>{KINDS[x.kind]}</Badge>
                  <span className={x.kind === "profile" ? "italic" : ""}>{x.kind === "profile" ? `“${x.evidence}”` : x.evidence}</span>
                  {x.source_url && <a href={x.source_url} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">source ↗</a>}
                </div>
              </li>
            ))}
          </ul>
          {row.gap && <p className="mt-2 text-sm"><span className="font-medium text-stone-800">Main gap: </span>{row.gap}</p>}
          {row.action && <p className="mt-1 text-sm"><span className="font-medium text-stone-800">Next step: </span>{row.action}</p>}
          <p className="mt-2 text-xs text-stone-400">
            By {by}{row.assessed_at ? ` · ${new Date(row.assessed_at).toLocaleDateString()}` : ""}
            {row.stale.length > 0 && ` · out of date: ${row.stale.join("; ")}`}
          </p>
        </>
      )}
    </div>
  );
}
