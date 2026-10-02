"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import type { Health } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/profile", label: "My profile" },
  { href: "/add", label: "Add professors" },
  { href: "/professors", label: "Professors" },
  { href: "/outreach", label: "Outreach" },
  { href: "/compare", label: "Compare" },
  { href: "/applications", label: "Applications" },
];

export default function Nav() {
  const path = usePathname();
  const { data: health, error } = useApi<Health>("/health");
  return (
    <header className="border-b border-stone-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        <Link href="/" className="text-lg font-bold text-stone-900">🐶 PhDDog</Link>
        <nav className="flex flex-wrap gap-1">
          {LINKS.map((l) => {
            const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
            return (
              <Link key={l.href} href={l.href}
                className={`rounded-md px-3 py-1.5 text-sm font-medium ${active ? "bg-indigo-50 text-indigo-700" : "text-stone-600 hover:bg-stone-100"}`}>
                {l.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto text-xs">
          {error ? (
            <span className="text-rose-700">API offline</span>
          ) : health ? (
            <span className={health.llm_provider === "fake" ? "text-amber-700" : "text-emerald-700"}
              title={health.llm_provider === "fake" ? "Running offline with rule-based stand-ins. Set LLM_PROVIDER=claude for real analysis." : ""}>
              LLM: {health.llm_provider === "fake" ? "offline (fake)" : health.llm_provider} · Target {health.target_cycle}
            </span>
          ) : null}
        </div>
      </div>
    </header>
  );
}
