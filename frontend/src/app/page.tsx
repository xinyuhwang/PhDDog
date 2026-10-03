"use client";

import Link from "next/link";

import { Card } from "@/components/ui";
import type { Application, Outreach, ProfessorSummary, Profile } from "@/lib/api";
import { useApi, useShowFit } from "@/lib/hooks";

export default function Dashboard() {
  const { data: profile } = useApi<Profile | null>("/profile");
  const { data: profs } = useApi<ProfessorSummary[]>("/professors");
  const { data: due } = useApi<Outreach[]>("/outreach?due=true");
  const { data: apps } = useApi<Application[]>("/applications");
  const upcoming = (apps ?? []).filter((a) => a.deadline && ["planning", "in_progress"].includes(a.status)).slice(0, 6);

  const showFit = useShowFit();
  const count = (f: (p: ProfessorSummary) => boolean) => profs?.filter(f).length ?? 0;
  const stats = [
    { label: "Professors", value: profs?.length ?? 0, href: "/professors" },
    showFit
      ? { label: "Strong fit", value: count((p) => p.screen?.label === "strong"), href: "/professors" }
      : { label: "Pinned", value: count((p) => p.pinned), href: "/professors" },
    { label: "Needs review", value: count((p) => ["needs_review", "not_found"].includes(p.resolve_status)), href: "/add" },
    { label: "Contacted", value: count((p) => ["contacted", "replied", "closed"].includes(p.status)), href: "/outreach" },
  ];

  const steps = [
    { done: !!profile, text: "Upload your resume and add a research statement", href: "/profile" },
    { done: (profs?.length ?? 0) > 0, text: "Add professors: “Name, School” — one per line", href: "/add" },
    { done: count((p) => p.pinned) > 0, text: "Pin professors (📌), then add their recent papers (PDF or link)", href: "/professors" },
    { done: count((p) => ["contacted", "replied", "closed"].includes(p.status)) > 0, text: "Draft an email, send it yourself, and log it", href: "/outreach" },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {stats.map((s) => (
          <Link key={s.label} href={s.href} className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm hover:border-indigo-300">
            <div className="text-2xl font-semibold">{s.value}</div>
            <div className="text-sm text-stone-500">{s.label}</div>
          </Link>
        ))}
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card title="Getting started">
          <ol className="space-y-2">
            {steps.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className={s.done ? "text-emerald-600" : "text-stone-400"}>{s.done ? "✓" : `${i + 1}.`}</span>
                <Link href={s.href} className={s.done ? "text-stone-500 line-through" : "text-stone-800 hover:text-indigo-700"}>{s.text}</Link>
              </li>
            ))}
          </ol>
        </Card>

        <Card title="Upcoming deadlines" actions={<Link href="/applications" className="text-sm text-indigo-600 hover:underline">Applications →</Link>}>
          {!upcoming.length ? <p className="text-sm text-stone-500">No application deadlines yet.</p> : (
            <ul className="divide-y divide-stone-100">
              {upcoming.map((a) => (
                <li key={a.id} className="flex items-center gap-3 py-2 text-sm">
                  <span className="w-24 text-stone-500">{new Date(`${a.deadline}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
                  <span className="flex-1">{a.school_name} <span className="text-stone-500">— {a.program}</span></span>
                  <span className={`text-xs ${(a.days_left ?? 99) <= 14 ? "font-medium text-amber-700" : "text-stone-500"}`}>{a.days_left}d · {a.done}/{a.total}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Follow-ups due">
          {!due?.length ? (
            <p className="text-sm text-stone-500">Nothing due. Follow-ups default to 14 days after sending.</p>
          ) : (
            <ul className="divide-y divide-stone-100">
              {due.map((o) => (
                <li key={o.id} className="py-2 text-sm">
                  <Link href={`/professors/${o.professor_id}`} className="font-medium hover:text-indigo-700">{o.professor_name}</Link>
                  <span className="text-stone-500"> · sent {new Date(o.sent_at).toLocaleDateString()} · {o.subject}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
