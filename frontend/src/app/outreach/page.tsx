"use client";

import Link from "next/link";
import { Fragment, useState } from "react";

import { Badge, Card, inputClass } from "@/components/ui";
import { api, type Outreach } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const STATUSES = ["sent", "no_response", "follow_up_sent", "replied", "meeting", "declined"];

export default function OutreachPage() {
  const { data, reload } = useApi<Outreach[]>("/outreach");
  const [open, setOpen] = useState<string | null>(null);
  const patch = async (id: string, body: Partial<Outreach>) => { await api.patch(`/outreach/${id}`, body); reload(); };

  return (
    <Card title={`Outreach log (${data?.length ?? 0})`}>
      {!data?.length ? <p className="text-sm text-stone-500">No emails logged yet. Draft one from a professor&apos;s page and click “Mark as sent”.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-stone-500">
              <tr><th className="py-2">Professor</th><th>Sent</th><th>Subject</th><th>Status</th><th>Follow up</th><th>Notes</th></tr>
            </thead>
            <tbody>
              {data.map((o) => {
                const due = o.follow_up_at && new Date(o.follow_up_at) < new Date() && ["sent", "no_response"].includes(o.status);
                return (
                  <Fragment key={o.id}>
                    <tr className="border-t border-stone-100 align-top">
                      <td className="py-2 pr-3">
                        <Link href={`/professors/${o.professor_id}`} className="font-medium hover:text-indigo-700">{o.professor_name}</Link>
                        <div className="text-xs text-stone-500">{o.school_name}</div>
                      </td>
                      <td className="pr-3 whitespace-nowrap">{new Date(o.sent_at).toLocaleDateString()}</td>
                      <td className="pr-3"><button className="text-left hover:text-indigo-700" onClick={() => setOpen(open === o.id ? null : o.id)}>{o.subject}</button></td>
                      <td className="pr-3">
                        <select className={`${inputClass} w-36 py-1 text-xs`} value={o.status} onChange={(e) => patch(o.id, { status: e.target.value })}>
                          {STATUSES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
                        </select>
                      </td>
                      <td className="pr-3">
                        <input type="date" className={`${inputClass} w-36 py-1 text-xs`} value={o.follow_up_at?.slice(0, 10) ?? ""}
                          onChange={(e) => patch(o.id, { follow_up_at: e.target.value ? new Date(e.target.value).toISOString() : null })} />
                        {due && <div className="mt-1"><Badge tone="yellow">Due</Badge></div>}
                      </td>
                      <td>
                        <input className={`${inputClass} py-1 text-xs`} defaultValue={o.notes ?? ""} placeholder="Add a note"
                          onBlur={(e) => e.target.value !== (o.notes ?? "") && patch(o.id, { notes: e.target.value })} />
                      </td>
                    </tr>
                    {open === o.id && (
                      <tr><td colSpan={6} className="pb-3">
                        <pre className="whitespace-pre-wrap rounded-md bg-stone-50 p-3 font-sans text-sm text-stone-700">To: {o.to_address ?? "—"}{"\n\n"}{o.body}</pre>
                      </td></tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
