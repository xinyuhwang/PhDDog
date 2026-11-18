"use client";

import Link from "next/link";

import { Card, ErrorNote } from "@/components/ui";
import type { Application, School } from "@/lib/api";
import { useApi } from "@/lib/hooks";

// Fees for the programs you're applying to: the one-time application fee, and what a funded
// PhD student still pays each year after tuition and insurance are covered. Stored in each
// application's requirements (fee, annual_fees_usd, annual_fees, annual_fees_source).
const money = (n: number) => (n === 0 ? "$0" : `~$${n.toLocaleString()}`);

export default function FeesPage() {
  const apps = useApi<Application[]>("/applications");
  const schools = useApi<School[]>("/schools");
  if (apps.error || schools.error) return <ErrorNote error={apps.error ?? schools.error} />;
  if (!apps.data || !schools.data) return <p className="text-sm text-stone-500">Loading…</p>;

  const selected = new Set(schools.data.filter((s) => s.is_target).map((s) => s.id));
  const rows = apps.data
    .filter((a) => selected.has(a.school_id) && a.decision !== "drop")
    .map((a) => {
      const raw = a.requirements.annual_fees_usd;
      return { a, annual: raw !== undefined && raw !== "" ? Number(raw) : null };
    })
    .sort((x, y) => (x.annual ?? Infinity) - (y.annual ?? Infinity) || x.a.school_name.localeCompare(y.a.school_name));
  const known = rows.filter((r) => r.annual !== null);
  const total = known.reduce((sum, r) => sum + (r.annual ?? 0), 0);

  return (
    <Card title={`Fees (${rows.length} programs)`}>
      <p className="mb-4 max-w-3xl text-sm text-stone-600">
        What each program you&apos;re applying to costs you. <span className="font-medium">Per year as a funded PhD student</span> is
        what you&apos;d still pay after tuition and health insurance are covered (2026–27 where posted). Where a page says
        &ldquo;if not covered&rdquo;, the school doesn&apos;t say either way, so check the offer letter.
      </p>
      {!rows.length ? (
        <p className="text-sm text-stone-500">No selected programs. Select schools on <Link href="/profile" className="text-indigo-600 hover:underline">My profile</Link>.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-stone-500">
              <tr>
                <th className="py-2 pr-3">Program</th>
                <th className="pr-3">Application fee</th>
                <th className="pr-3">Per year as a funded PhD student</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ a, annual }) => (
                <tr key={a.id} className="border-t border-stone-100 align-top">
                  <td className="py-2.5 pr-3">
                    <div className="font-medium text-stone-900">{a.school_name}</div>
                    <div className="text-xs text-stone-500">{a.program}</div>
                    {(a.requirements.location || a.requirements.calendar) && (
                      <div className="mt-0.5 text-xs text-stone-500">
                        {[a.requirements.location && `📍 ${a.requirements.location}`, a.requirements.calendar && `${a.requirements.calendar} calendar`].filter(Boolean).join(" · ")}
                      </div>
                    )}
                  </td>
                  <td className="max-w-xs pr-3 text-stone-700">{a.requirements.fee || <span className="text-stone-400">Not recorded</span>}</td>
                  <td className="max-w-md py-2.5 pr-3">
                    {annual === null ? <span className="text-stone-400">Not researched</span> : (
                      <>
                        <div className="font-semibold text-stone-900">{money(annual)}</div>
                        {a.requirements.annual_fees && <div className="mt-0.5 text-xs text-stone-600">{a.requirements.annual_fees}</div>}
                        {a.requirements.annual_fees_source && (
                          <a href={a.requirements.annual_fees_source} target="_blank" rel="noreferrer" className="text-xs text-indigo-600 hover:underline">Source ↗</a>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {known.length > 1 && (
            <p className="mt-3 text-xs text-stone-500">
              Range across researched programs: {money(Math.min(...known.map((r) => r.annual ?? 0)))} to {money(Math.max(...known.map((r) => r.annual ?? 0)))} a year
              (average {money(Math.round(total / known.length))}). Small next to the stipend at every school.
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
