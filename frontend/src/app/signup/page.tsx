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
    <main className="flex h-full flex-col items-center justify-center overflow-y-auto px-6 py-16">
      <div className="w-full max-w-sm">
        <h1 className="text-display font-semibold tracking-tight">Create account</h1>
        <p className="measure mt-2 text-body text-zinc-400">
          Set up an account to start training models and deploying them.
        </p>

        {error && (
          <div className="fade-in mt-6 flex items-start gap-2.5 rounded-lg border border-red-900 bg-red-950/50 px-4 py-3 text-body text-red-300">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-red-500" />
            <span>
              {error}
              {emailTaken && (
                <>
                  {" "}
                  <Link
                    href="/login"
                    className="focus-ring rounded font-medium text-red-200 underline transition-colors hover:text-red-100"
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
              className="focus-ring w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-body text-zinc-100 outline-none placeholder:text-zinc-400 focus:border-emerald-600"
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
              className="focus-ring w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-body text-zinc-100 outline-none placeholder:text-zinc-400 focus:border-emerald-600"
            />
          </div>

          <button
            type="submit"
            disabled={busy}
            className="focus-ring w-full rounded-lg bg-emerald-600 px-4 py-2.5 text-body font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-40"
          >
            {busy ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="measure mt-4 text-label text-zinc-400">
          Already have an account?{" "}
          <Link
            href="/login"
            className="focus-ring rounded text-emerald-400 transition-colors hover:text-emerald-300"
          >
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
