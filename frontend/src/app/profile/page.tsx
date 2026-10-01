"use client";

import { useEffect, useState } from "react";

import TargetSchools from "@/components/TargetSchools";
import { Badge, Button, Card, ErrorNote, inputClass } from "@/components/ui";
import { api, type Profile } from "@/lib/api";
import { useApi } from "@/lib/hooks";

export default function ProfilePage() {
  const { data: profile, setData } = useApi<Profile | null>("/profile");
  const [statement, setStatement] = useState("");
  const [keywords, setKeywords] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (profile) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync form with loaded profile
      setStatement(profile.research_statement ?? "");
      setKeywords(profile.keywords.join(", "));
    }
  }, [profile]);

  async function run(fn: () => Promise<Profile>) {
    setBusy(true);
    setError(null);
    try {
      setData(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const sp = profile?.structured_profile;
  return (
    <div className="space-y-6">
    <TargetSchools />
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-6">
        <Card title="Resume">
          <p className="mb-3 text-sm text-stone-600">
            {profile?.resume_text ? `Resume loaded (${profile.resume_text.length.toLocaleString()} characters). Upload again to replace it.` : "Upload your resume as a PDF."}
          </p>
          <input type="file" accept="application/pdf" disabled={busy}
            className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-indigo-50 file:px-3 file:py-1.5 file:text-indigo-700"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) run(() => api.upload<Profile>("/profile/resume", f)); }} />
        </Card>

        <Card title="Research interests">
          <label className="mb-1 block text-sm font-medium">Research statement</label>
          <textarea className={`${inputClass} h-40`} value={statement} onChange={(e) => setStatement(e.target.value)}
            placeholder="e.g. I build machine learning methods for medical imaging and clinical decision support…" />
          <label className="mb-1 mt-4 block text-sm font-medium">Keywords (comma-separated)</label>
          <input className={inputClass} value={keywords} onChange={(e) => setKeywords(e.target.value)}
            placeholder="health AI, medical imaging, EHR, drug discovery" />
          <div className="mt-4 flex items-center gap-3">
            <Button disabled={busy} onClick={() => run(() => api.put<Profile>("/profile", {
              research_statement: statement, keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean),
            }))}>Save</Button>
            {profile && <span className="text-xs text-stone-500">Version {profile.version} · changes create a new version; re-run screening after</span>}
          </div>
          <div className="mt-3"><ErrorNote error={error} /></div>
        </Card>
      </div>

      <Card title="What the app understood">
        {!sp ? <p className="text-sm text-stone-500">Upload a resume or save a statement to see your structured profile.</p> : (
          <div className="space-y-4 text-sm">
            {[["Domains", sp.domains], ["Methods", sp.methods], ["Skills", sp.skills]].map(([label, items]) => (
              <div key={label as string}>
                <div className="mb-1 font-medium">{label as string}</div>
                <div className="flex flex-wrap gap-1">
                  {(items as string[]).length ? (items as string[]).map((t) => <Badge key={t} tone="blue">{t}</Badge>) : <span className="text-stone-400">none found</span>}
                </div>
              </div>
            ))}
            <div>
              <div className="mb-1 font-medium">Experience used as evidence in emails</div>
              <ul className="list-disc space-y-1 pl-5 text-stone-700">
                {sp.experiences.map((x, i) => <li key={i}>{x.description}</li>)}
                {!sp.experiences.length && <li className="list-none text-stone-400">none found</li>}
              </ul>
            </div>
          </div>
        )}
      </Card>
    </div>
    </div>
  );
}
