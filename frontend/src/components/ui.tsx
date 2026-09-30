import type { ReactNode } from "react";

const TONES = {
  green: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  yellow: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-rose-50 text-rose-800 ring-rose-200",
  blue: "bg-sky-50 text-sky-800 ring-sky-200",
  gray: "bg-stone-100 text-stone-600 ring-stone-200",
} as const;
type Tone = keyof typeof TONES;

export function Badge({ tone = "gray", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone]}`}>
      {children}
    </span>
  );
}

const FIT: Record<string, [Tone, string]> = { strong: ["green", "Strong fit"], possible: ["yellow", "Possible"], no: ["gray", "No fit"] };
const RECRUITING: Record<string, [Tone, string]> = {
  explicitly_recruiting: ["green", "Recruiting"],
  recruits_generally: ["blue", "Recruits yearly"],
  not_recruiting: ["red", "Not recruiting"],
  unknown: ["gray", "Unknown"],
};
const CONTACT: Record<string, [Tone, string]> = {
  welcomes_email: ["green", "Email OK"],
  apply_via_program: ["yellow", "Apply via program"],
  do_not_email: ["red", "Don't email"],
  unknown: ["gray", "Unknown"],
};
const RESOLVE: Record<string, [Tone, string]> = {
  pending: ["blue", "Looking up…"],
  resolved: ["green", "Found"],
  needs_review: ["yellow", "Needs review"],
  not_found: ["red", "Not found"],
};

const STAGES: Record<string, [Tone, string, string]> = {
  added: ["blue", "Looking up", "Finding and reading their homepage"],
  resolved: ["gray", "New", "Homepage read; not shortlisted yet"],
  screened: ["gray", "New", "Homepage read; not shortlisted yet"],
  shortlisted: ["blue", "Shortlisted", "Next: add their recent papers"],
  analyzed: ["blue", "Papers analyzed", "Next: draft an email"],
  drafted: ["yellow", "Email drafted", "Next: send it and mark as sent"],
  contacted: ["green", "Contacted", "Email sent; waiting for a reply"],
  replied: ["green", "Replied", "They replied"],
  closed: ["gray", "Closed", "Declined or no longer pursuing"],
  dismissed: ["gray", "Dismissed", "Hidden from the list by default"],
};

/** Where this professor is in your outreach: Looking up → New → Shortlisted → Papers analyzed → Email drafted → Contacted → Replied. */
export function StageBadge({ status }: { status: string }) {
  const [tone, text, hint] = STAGES[status] ?? ["gray", status, ""];
  return <Badge tone={tone} title={hint}>{text}</Badge>;
}

export function FitBadge({ label, reason }: { label?: string; reason?: string }) {
  if (!label) return <Badge title="Needs your profile and the professor's research interests">Not screened</Badge>;
  const [tone, text] = FIT[label] ?? ["gray", label];
  return <Badge tone={tone} title={reason}>{text}</Badge>;
}

export function RecruitingBadge({ status, cycle, stale }: { status: string; cycle?: string | null; stale?: boolean }) {
  const [tone, text] = RECRUITING[status] ?? ["gray", status];
  return (
    <span className="inline-flex flex-wrap gap-1">
      <Badge tone={stale ? "yellow" : tone}>{text}{cycle ? ` · ${cycle}` : ""}</Badge>
      {stale && <Badge tone="yellow" title="The cycle mentioned is earlier than your target cycle">Stale</Badge>}
    </span>
  );
}

export function ContactBadge({ policy }: { policy: string }) {
  const [tone, text] = CONTACT[policy] ?? ["gray", policy];
  return <Badge tone={tone}>{text}</Badge>;
}

export function ResolveBadge({ status }: { status: string }) {
  const [tone, text] = RESOLVE[status] ?? ["gray", status];
  return <Badge tone={tone}>{text}</Badge>;
}

export function Card({ title, actions, children }: { title?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-stone-200 bg-white p-5 shadow-sm">
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-base font-semibold text-stone-900">{title}</h2>}
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Button({
  children, onClick, variant = "primary", disabled, type = "button",
}: {
  children: ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "danger"; disabled?: boolean; type?: "button" | "submit";
}) {
  const styles = {
    primary: "bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-indigo-300",
    secondary: "bg-white text-stone-700 ring-1 ring-inset ring-stone-300 hover:bg-stone-50 disabled:text-stone-400",
    danger: "bg-white text-rose-700 ring-1 ring-inset ring-rose-300 hover:bg-rose-50",
  }[variant];
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${styles}`}>
      {children}
    </button>
  );
}

export function ErrorNote({ error }: { error: string | null | undefined }) {
  if (!error) return null;
  return <p className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</p>;
}

export function Quote({ text, url }: { text: string; url?: string | null }) {
  return (
    <blockquote className="border-l-2 border-stone-300 pl-3 text-sm italic text-stone-700">
      “{text}”
      {url && (
        <a href={url} target="_blank" rel="noreferrer" className="ml-2 not-italic text-indigo-600 hover:underline">
          source ↗
        </a>
      )}
    </blockquote>
  );
}

export const inputClass =
  "w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm text-stone-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500";
