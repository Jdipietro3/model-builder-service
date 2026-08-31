"use client";

/**
 * Pre-auth sign-in screen.
 *
 * Deliberately renders no <Sidebar> — this is the one screen a signed-out
 * visitor can always reach, since apiFetch (see lib/api.ts) sends them here
 * the instant any protected call comes back 401. There is no client-side
 * route guard anywhere in the app; the backend's 401 IS the guard, and this
 * page is where it lands people.
 */

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useProjects } from "@/lib/projects-context";
import { extractErrorDetail } from "@/lib/errors";

export default function LoginPage() {
  const router = useRouter();
  // ProjectsProvider (root layout) fetched the project list + user before
  // this form even existed on screen, both of which 401'd for a signed-out
  // visitor. Calling refresh() after a successful login re-runs both so the
  // rail is populated the moment we navigate to `/` — router.push alone
  // wouldn't remount the provider to trigger that fetch on its own.
  const { refresh } = useProjects();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.login(email, password);
      await refresh();
      router.push("/");
    } catch (err) {
      setError(extractErrorDetail(err));
      setBusy(false);
    }
  }

  return (
    <main className="flex h-full flex-col items-center justify-center overflow-y-auto px-6 py-16">
      <div className="w-full max-w-sm">
        <h1 className="text-display font-semibold tracking-tight">Sign in</h1>
        <p className="measure mt-2 text-body text-zinc-400">
          Sign in to pick up your projects, models, and deployments where you left off.
        </p>

        {error && (
          <div className="fade-in mt-6 flex items-start gap-2.5 rounded-lg border border-red-900 bg-red-950/50 px-4 py-3 text-body text-red-300">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-red-500" />
            <span>{error}</span>
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
              autoComplete="current-password"
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
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="measure mt-4 text-label text-zinc-400">
          Don&rsquo;t have an account?{" "}
          <Link
            href="/signup"
            className="focus-ring rounded text-emerald-400 transition-colors hover:text-emerald-300"
          >
            Create one
          </Link>
        </p>
      </div>
    </main>
  );
}
