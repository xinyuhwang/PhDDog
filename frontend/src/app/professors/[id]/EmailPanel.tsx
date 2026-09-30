"use client";

import { useEffect, useState } from "react";

import { Badge, Button, Card, ErrorNote, inputClass, Quote } from "@/components/ui";
import { api, type ConnectionPoint, type Draft, type Outreach, type ProfessorDetail } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const OUTREACH_STATUSES = ["sent", "no_response", "follow_up_sent", "replied", "meeting", "declined"];

export default function EmailPanel({ prof, onChanged }: { prof: ProfessorDetail; onChanged: () => void }) {
  const drafts = useApi<Draft[]>(`/professors/${prof.id}/drafts`);
  const outreach = useApi<Outreach[]>("/outreach");
  const [tone, setTone] = useState("formal");
  const [ask, setAsk] = useState("both");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [to, setTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);

  const current = drafts.data?.find((d) => d.id === selectedId) ?? drafts.data?.[0];
  useEffect(() => {
    if (current) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- load the chosen version into the editor
      setSubject(current.subject);
      setBody(current.body);
    }
  }, [current]);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- default recipient from their site
    setTo(prof.email ?? "");
  }, [prof.email]);

  const history = outreach.data?.filter((o) => o.professor_id === prof.id) ?? [];
  const cautious = prof.contact_policy === "do_not_email" || prof.contact_policy === "apply_via_program";
  const dirty = current && (subject !== current.subject || body !== current.body);

  async function act<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setError(null);
    try {
      const out = await fn();
      await Promise.all([drafts.reload(), outreach.reload()]);
      onChanged();
      return out;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function generate() {
    const conns = await api.get<ConnectionPoint[]>(`/professors/${prof.id}/connections`);
    const draft = await act(() => api.post<Draft>(`/professors/${prof.id}/drafts`, {
      connection_point_ids: conns.filter((c) => c.selected).map((c) => c.id), tone, ask,
    }));
    if (draft) setSelectedId(draft.id);
  }

  return (
    <div id="email" className="grid scroll-mt-4 gap-6 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <Card title="Email draft">
          {cautious && (
            <div className="mb-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm">
              <p className="mb-2 font-medium text-amber-900">
                {prof.contact_policy === "do_not_email" ? "This professor asks not to be emailed about admissions." : "This professor asks applicants to apply through the program."}
              </p>
              {prof.contact_evidence && <Quote text={prof.contact_evidence} url={prof.contact_source_url} />}
              <label className="mt-2 flex items-center gap-2 text-amber-900">
                <input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />
                I understand — I&apos;ll ask about a specific paper or RA role, not admissions.
              </label>
            </div>
          )}

          <div className="mb-4 flex flex-wrap items-end gap-3 text-sm">
            <label>Tone
              <select className={`${inputClass} mt-1 w-32 py-1`} value={tone} onChange={(e) => setTone(e.target.value)}>
                <option value="formal">Formal</option><option value="warm">Warm</option>
              </select>
            </label>
            <label>Ask about
              <select className={`${inputClass} mt-1 w-44 py-1`} value={ask} onChange={(e) => setAsk(e.target.value)}>
                <option value="both">PhD + RA</option><option value="phd">PhD only</option><option value="ra">RA only</option>
              </select>
            </label>
            <Button disabled={cautious && !acknowledged} onClick={generate}>{drafts.data?.length ? "Generate new draft" : "Generate draft"}</Button>
            {!!drafts.data?.length && (
              <label>Version
                <select className={`${inputClass} mt-1 w-56 py-1`} value={current?.id} onChange={(e) => setSelectedId(e.target.value)}>
                  {drafts.data.map((d) => <option key={d.id} value={d.id}>v{d.version} · {d.edited_by_user ? "your edit" : `generated (${d.model})`}</option>)}
                </select>
              </label>
            )}
          </div>

          {current ? (
            <div className="space-y-3">
              <input className={inputClass} value={subject} onChange={(e) => setSubject(e.target.value)} />
              <textarea className={`${inputClass} h-72 font-mono text-[13px]`} value={body} onChange={(e) => setBody(e.target.value)} />
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-xs text-stone-500">{body.split(/\s+/).filter(Boolean).length} words</span>
                <Button variant="secondary" disabled={!dirty} onClick={async () => { const d = await act(() => api.put<Draft>(`/drafts/${current.id}`, { subject, body })); if (d) setSelectedId(d.id); }}>Save as new version</Button>
                <Button variant="secondary" onClick={() => navigator.clipboard.writeText(`${subject}\n\n${body}`)}>Copy</Button>
                <span className="ml-auto" />
                <input className={`${inputClass} w-64 py-1`} value={to} onChange={(e) => setTo(e.target.value)} placeholder="To: email" />
                <Button disabled={!!dirty} onClick={() => act(() => api.post(`/professors/${prof.id}/outreach`, { draft_id: current.id, to_address: to || null }))}>
                  Mark as sent
                </Button>
              </div>
              {dirty && <p className="text-xs text-amber-700">Save your edits as a new version before marking as sent, so the log keeps the exact text.</p>}
              <p className="text-xs text-stone-500">Send it from your own email, then click “Mark as sent” to log it.</p>
            </div>
          ) : <p className="text-sm text-stone-500">Select connection points above, then generate a draft.</p>}
          <div className="mt-3"><ErrorNote error={error} /></div>
        </Card>
      </div>

      <Card title="Outreach log">
        {!history.length ? <p className="text-sm text-stone-500">Nothing sent yet.</p> : (
          <ul className="space-y-3">
            {history.map((o) => (
              <li key={o.id} className="text-sm">
                <div className="font-medium">{o.subject}</div>
                <div className="text-xs text-stone-500">Sent {new Date(o.sent_at).toLocaleDateString()} to {o.to_address ?? "—"}</div>
                <div className="mt-1 flex items-center gap-2">
                  <select className={`${inputClass} w-40 py-1 text-xs`} value={o.status}
                    onChange={(e) => act(() => api.patch(`/outreach/${o.id}`, { status: e.target.value }))}>
                    {OUTREACH_STATUSES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
                  </select>
                  {o.follow_up_at && <Badge tone={new Date(o.follow_up_at) < new Date() ? "yellow" : "gray"}>Follow up {new Date(o.follow_up_at).toLocaleDateString()}</Badge>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
