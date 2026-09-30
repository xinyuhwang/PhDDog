"use client";

import { useState } from "react";

import { Badge, Button, Card, ErrorNote, inputClass, Quote } from "@/components/ui";
import { api, type ConnectionPoint, type Paper } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const TEXT_STATUS: Record<string, ["green" | "yellow" | "red" | "blue", string]> = {
  pending: ["blue", "Fetching…"],
  full: ["green", "Full text"],
  abstract_only: ["yellow", "Abstract only — upload the PDF for a deeper read"],
  failed: ["red", "Couldn't get text"],
};
const KIND_LABEL: Record<string, string> = {
  method_overlap: "Method overlap",
  domain_overlap: "Domain overlap",
  future_work_hook: "Future-work hook",
};

export default function PapersPanel({ professorId, onJob, busy }: { professorId: string; onJob: () => void; busy: boolean }) {
  const papers = useApi<Paper[]>(`/professors/${professorId}/papers`, (d) => busy || d.some((p) => p.text_status === "pending" || (p.text_status !== "failed" && !p.summary)));
  const connections = useApi<ConnectionPoint[]>(`/professors/${professorId}/connections`, () => busy);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      onJob();
      papers.reload();
      connections.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const summarized = papers.data?.filter((p) => p.summary).length ?? 0;

  return (
    <div id="papers" className="grid scroll-mt-4 gap-6 lg:grid-cols-2">
      <Card title="Their papers">
        <p className="mb-3 text-sm text-stone-600">Add recent papers (ideally this year and last) as a PDF or a link — arXiv, bioRxiv/medRxiv, PubMed, DOI, or any article page.</p>
        <div className="flex gap-2">
          <input className={inputClass} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://arxiv.org/abs/… or DOI link" />
          <Button disabled={!url} onClick={() => act(async () => { await api.post(`/professors/${professorId}/papers/url`, { url }); setUrl(""); })}>Add link</Button>
        </div>
        <div className="mt-2 text-sm">
          <label className="text-stone-600">or upload PDF: </label>
          <input type="file" accept="application/pdf" className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-indigo-50 file:px-3 file:py-1 file:text-indigo-700"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) act(() => api.upload(`/professors/${professorId}/papers/pdf`, f)); e.target.value = ""; }} />
        </div>
        <div className="mt-3"><ErrorNote error={error} /></div>

        <ul className="mt-4 divide-y divide-stone-100">
          {papers.data?.map((p) => {
            const [tone, label] = TEXT_STATUS[p.text_status];
            return (
              <li key={p.id} className="py-3 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <button className="text-left font-medium hover:text-indigo-700" onClick={() => setOpen(open === p.id ? null : p.id)}>
                    {p.title ?? p.source_url ?? "Untitled"}
                  </button>
                  <button className="text-xs text-stone-400 hover:text-rose-600" onClick={() => act(() => api.del(`/papers/${p.id}`))}>remove</button>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  <Badge tone={tone}>{label}</Badge>
                  {p.year && <Badge tone={p.year_warning ? "yellow" : "gray"} title={p.year_warning ? "Older than your paper window" : ""}>{p.year}{p.year_warning ? " · older" : ""}</Badge>}
                  {p.venue && <Badge>{p.venue}</Badge>}
                  {p.text_status !== "pending" && p.text_status !== "failed" && !p.summary && <Badge tone="blue">Summarizing…</Badge>}
                </div>
                {p.error && <p className="mt-1 text-xs text-stone-500">{p.error}</p>}
                {open === p.id && p.summary && (
                  <dl className="mt-2 space-y-1 rounded-md bg-stone-50 p-3 text-xs">
                    {p.summary.problem && <div><dt className="inline font-semibold">Problem: </dt><dd className="inline">{p.summary.problem}</dd></div>}
                    {[["Methods", p.summary.methods], ["Data", p.summary.data_modalities], ["Findings", p.summary.key_findings], ["Limitations", p.summary.limitations], ["Future work", p.summary.future_work]]
                      .filter(([, v]) => (v as string[]).length)
                      .map(([k, v]) => <div key={k as string}><dt className="inline font-semibold">{k as string}: </dt><dd className="inline">{(v as string[]).join(" · ")}</dd></div>)}
                    {p.summary.application_setting && <div><dt className="inline font-semibold">Setting: </dt><dd className="inline">{p.summary.application_setting}</dd></div>}
                  </dl>
                )}
              </li>
            );
          })}
        </ul>
      </Card>

      <Card title="Connection points" actions={
        <Button disabled={!summarized || busy} onClick={() => act(() => api.post(`/professors/${professorId}/analyze`))}>
          {busy ? "Working…" : connections.data?.length ? "Re-analyze" : "Find connections"}
        </Button>
      }>
        {!connections.data?.length ? (
          <p className="text-sm text-stone-500">{summarized ? "Compare their papers with your resume to find specific overlaps." : "Add at least one paper first."}</p>
        ) : (
          <>
            <p className="mb-3 text-xs text-stone-500">Select the ones to use in the email.</p>
            <ul className="space-y-3">
              {connections.data.map((c) => (
                <li key={c.id} className={`rounded-md border p-3 text-sm ${c.selected ? "border-indigo-300 bg-indigo-50/40" : "border-stone-200"}`}>
                  <label className="flex items-start gap-2">
                    <input type="checkbox" className="mt-1" checked={c.selected}
                      onChange={(e) => act(() => api.patch(`/connections/${c.id}`, { selected: e.target.checked }))} />
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2"><Badge tone="blue">{KIND_LABEL[c.kind]}</Badge><span className="text-xs text-stone-500">{c.paper_title}</span></div>
                      <p>{c.explanation}</p>
                      <div className="text-xs text-stone-500">Their paper:</div><Quote text={c.paper_evidence} />
                      <div className="text-xs text-stone-500">Your resume:</div><Quote text={c.user_evidence} />
                    </div>
                  </label>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>
    </div>
  );
}
