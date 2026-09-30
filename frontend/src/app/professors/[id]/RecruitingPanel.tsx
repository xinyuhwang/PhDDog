"use client";

import { useState } from "react";

import { Badge, Button, Card, ContactBadge, Quote, RecruitingBadge } from "@/components/ui";
import type { Evidence, ProfessorDetail } from "@/lib/api";

const SOURCE_LABEL: Record<string, string> = {
  personal: "Personal site",
  lab: "Lab",
  faculty_profile: "Faculty profile",
  department: "Department",
  admissions: "Admissions",
  other: "Other",
};
const CLAIM_LABEL: Record<string, string> = {
  explicitly_recruiting: "Recruiting",
  recruits_generally: "Recruits yearly",
  not_recruiting: "Not recruiting",
  welcomes_email: "Email OK",
  apply_via_program: "Apply via program",
  do_not_email: "Don't email",
};
const CONFIDENCE: Record<string, ["green" | "yellow" | "gray", string, string]> = {
  high: ["green", "High confidence", "Names your target cycle, on their own page"],
  medium: ["gray", "Medium confidence", "Their own page, but undated or a general statement"],
  low: ["yellow", "Low confidence", "Names an earlier cycle, or isn't from their own page"],
};

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "");

function EvidenceItem({ e }: { e: Evidence }) {
  return (
    <li className={`space-y-1 ${e.gone_at ? "opacity-60" : ""}`}>
      <div className="flex flex-wrap items-center gap-1">
        <Badge tone="blue">{SOURCE_LABEL[e.source_type] ?? e.source_type}</Badge>
        <Badge>{CLAIM_LABEL[e.claim] ?? e.claim}{e.cycle ? ` · ${e.cycle}` : ""}</Badge>
        {e.extractor === "fake" && <Badge title="Found by offline keyword rules">rule-based</Badge>}
      </div>
      <Quote text={e.quote} url={e.source_url} />
      <p className="text-xs text-stone-500">
        {e.gone_at ? `No longer on the page since ${day(e.gone_at)} · ` : ""}
        First seen {day(e.first_seen_at)}{e.gone_at ? "" : ` · last seen ${day(e.last_seen_at)}`}
        {e.page_updated_at && ` · page updated ${day(e.page_updated_at)}`}
      </p>
    </li>
  );
}

export default function RecruitingPanel({
  prof, targetCycle, busy, onRecheck,
}: { prof: ProfessorDetail; targetCycle: string; busy: boolean; onRecheck: () => void }) {
  const [showHistory, setShowHistory] = useState(false);
  const current = prof.evidence.filter((e) => !e.gone_at);
  const gone = prof.evidence.filter((e) => e.gone_at);
  const recruiting = current.filter((e) => e.kind === "recruiting");
  const contact = current.filter((e) => e.kind === "contact_policy");
  const noRecent = prof.recruiting_status === "unknown" || prof.recruiting_stale;
  const confidence = prof.recruiting_confidence ? CONFIDENCE[prof.recruiting_confidence] : null;
  const recheck = <Button variant="secondary" disabled={busy || !prof.homepage_url} onClick={onRecheck}>{busy ? "Checking…" : "Re-check site"}</Button>;

  return (
    <Card title="Recruiting & contact policy" actions={recheck}>
      <div className="space-y-5 text-sm">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2 font-medium">
            PhD recruiting <RecruitingBadge status={prof.recruiting_status} cycle={prof.recruiting_cycle} stale={prof.recruiting_stale} />
            {confidence && <Badge tone={confidence[0]} title={confidence[2]}>{confidence[1]}</Badge>}
          </div>

          {noRecent && (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-900">
              <p className="font-medium">⚠️ {prof.recruiting_status === "unknown" ? "No recruiting evidence found" : "Only older evidence"}</p>
              <p className="mt-1">
                {prof.recruiting_status === "unknown"
                  ? `Their pages don't say whether they're taking students for ${targetCycle}.`
                  : `The latest statement is about ${prof.recruiting_cycle}; it doesn't confirm ${targetCycle}.`}
                {" "}Last checked {day(prof.last_checked_at) || "never"}.
              </p>
            </div>
          )}
          {prof.check_stale && !noRecent && (
            <p className="text-xs text-amber-700">Last checked {day(prof.last_checked_at)} — pages may have changed. Re-check to confirm.</p>
          )}

          {recruiting.length > 0 && <ul className="space-y-3">{recruiting.map((e) => <EvidenceItem key={e.id} e={e} />)}</ul>}
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-2 font-medium">Contact policy <ContactBadge policy={prof.contact_policy} /></div>
          {contact.length ? <ul className="space-y-3">{contact.map((e) => <EvidenceItem key={e.id} e={e} />)}</ul>
            : <p className="text-stone-500">No statement about emailing them found.</p>}
        </div>

        {gone.length > 0 && (
          <div>
            <button className="text-xs text-indigo-600 hover:underline" onClick={() => setShowHistory(!showHistory)}>
              {showHistory ? "Hide" : "Show"} history ({gone.length} statement{gone.length === 1 ? "" : "s"} no longer on their pages)
            </button>
            {showHistory && <ul className="mt-2 space-y-3">{gone.map((e) => <EvidenceItem key={e.id} e={e} />)}</ul>}
          </div>
        )}

        <p className="text-xs text-stone-500">
          Checked {prof.pages.filter((p) => p.fetch_status === "ok").length} page(s)
          {prof.last_checked_at && ` · ${new Date(prof.last_checked_at).toLocaleString()}`}
        </p>
        {prof.pages.some((p) => p.fetch_status !== "ok") && (
          <div className="text-xs text-stone-600">
            Couldn&apos;t read (the site blocks automated visits or is down) — worth a look yourself:
            <ul className="mt-1 list-disc pl-5">
              {prof.pages.filter((p) => p.fetch_status !== "ok").map((p) => (
                <li key={p.url}><a href={p.url} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">{p.url}</a>
                  {p.error?.includes("403") && " (blocked)"}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}
