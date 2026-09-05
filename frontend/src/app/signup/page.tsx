"use client";

/**
 * Pre-auth account-creation screen. See login/page.tsx for why this renders
 * no <Sidebar> and why a successful submit calls refresh() before navigating.
 */

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useProjects } from "@/lib/projects-context";
import { extractErrorDetail } from "@/lib/errors";
import MetisMark from "@/components/MetisMark";
import GlyphField from "@/components/GlyphField";

/** apiFetch/json both throw `${status}: ${body}` (see lib/api.ts) — a stable
 *  prefix to branch on without parsing the body first. */
function isEmailTaken(e: unknown): boolean {
  return String(e instanceof Error ? e.message : e).startsWith("409:");
}

export default function SignupPage() {
  const router = useRouter();
  const { refresh } = useProjects();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emailTaken, setEmailTaken] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setEmailTaken(false);
    try {
      await api.signup(email, password);
      await refresh();
      router.push("/");
    } catch (err) {
      if (isEmailTaken(err)) {
        setEmailTaken(true);
        setError("An account with that email already exists.");
      } else {
        setError(extractErrorDetail(err));
      }
      setBusy(false);
    }
  }

  return (
    <main className="relative flex h-full flex-col items-center justify-center overflow-y-auto px-6 py-16">
      <GlyphField />

      <div className="relative z-10 w-full max-w-sm rounded-xl border border-accent-edge bg-zinc-950 p-8">
        <div className="flex items-center justify-center gap-2">
          <MetisMark size={28} className="text-accent" />
          <span className="text-headline font-semibold tracking-tight text-zinc-100">Metis</span>
        </div>

        <h1 className="mt-8 text-display font-semibold tracking-tight">Create account</h1>
        <p className="measure mt-2 text-body text-zinc-400">
          Set up an account to start training models and deploying them.
        </p>

        {error && (
          <div className="fade-in mt-6 flex items-start gap-2.5 rounded-lg bg-alarm-wash px-4 py-3 text-body text-alarm">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-alarm" />
            <span>
              {error}
              {emailTaken && (
                <>
                  {" "}
                  <Link
                    href="/login"
                    className="focus-ring rounded font-medium text-alarm underline transition-colors hover:opacity-80"
                  >
                    Sign in instead
                  </Link>
                </>
              )}
            </span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-8 space-y-4">
          <div>
            <label htmlFor="email" className="mb-1.5 block text-label text-zinc-400">
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="focus-ring w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-body text-zinc-100 outline-none placeholder:text-zinc-400 focus:border-accent-edge"
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-1.5 block text-label text-zinc-400">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="focus-ring w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-body text-zinc-100 outline-none placeholder:text-zinc-400 focus:border-accent-edge"
            />
          </div>

          <button
            type="submit"
            disabled={busy}
            className="focus-ring w-full rounded-lg bg-accent px-4 py-2.5 text-body font-medium text-accent-ink transition-colors hover:bg-accent-bright disabled:opacity-40"
          >
            {busy ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="measure mt-4 text-label text-zinc-400">
          Already have an account?{" "}
          <Link
            href="/login"
            className="focus-ring rounded text-accent transition-colors hover:text-accent-bright"
          >
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
