"use client";

/**
 * Signed-in account settings: view the signed-in email, change password, and
 * a "sign out everywhere" escape hatch. Unlike login/signup this renders
 * <Sidebar /> — it's a page you reach only once authenticated.
 */

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useProjects } from "@/lib/projects-context";
import { extractErrorDetail } from "@/lib/errors";
import Sidebar from "@/components/Sidebar";

const MIN_PASSWORD_LENGTH = 8;

export default function AccountPage() {
  const router = useRouter();
  const { user } = useProjects();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [signingOutAll, setSigningOutAll] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);

  async function handleChangePassword(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setSuccess(false);

    // Checked client-side first — a round trip just to be told the two
    // fields don't match is a poor experience the backend can't prevent.
    if (newPassword !== confirmPassword) {
      setError("New passwords don't match.");
      return;
    }
    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      setError(`New password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    setBusy(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setSuccess(true);
    } catch (err) {
      setError(extractErrorDetail(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSignOutAll() {
    if (signingOutAll) return;
    setSigningOutAll(true);
    setSignOutError(null);
    try {
      await api.logoutAll();
      router.push("/login");
    } catch (err) {
      setSignOutError(extractErrorDetail(err));
      setSigningOutAll(false);
    }
  }

  return (
    <div className="flex h-full">
      <Sidebar />

      <main className="flex min-w-0 flex-1 flex-col overflow-y-auto px-6 py-16">
        <div className="mx-auto w-full max-w-sm">
          <h1 className="text-display font-semibold tracking-tight">Account</h1>

          <section className="mt-8">
            <h2 className="text-headline font-semibold">Account</h2>
            <p className="measure mt-2 text-body text-zinc-400">
              Signed in as{" "}
              <span className="font-mono text-xs text-zinc-300">{user?.email}</span>
            </p>
          </section>

          <section className="mt-10 border-t border-zinc-800 pt-8">
            <h2 className="text-headline font-semibold">Change password</h2>
            <p className="measure mt-2 text-body text-zinc-400">
              Changing your password signs you out of every other device — this one stays
              signed in.
            </p>

            {error && (
              <div className="fade-in mt-4 flex items-start gap-2.5 rounded-lg border border-red-900 bg-red-950/50 px-4 py-3 text-body text-red-300">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-red-500" />
                <span>{error}</span>
              </div>
            )}

            {success && (
              <div className="fade-in mt-4 flex items-start gap-2.5 rounded-lg border border-emerald-800 bg-emerald-950/30 px-4 py-3 text-body text-emerald-300">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                <span>Password changed. You&rsquo;ve been signed out on every other device.</span>
              </div>
            )}

            <form onSubmit={handleChangePassword} className="mt-6 space-y-4">
              <div>
                <label
                  htmlFor="current-password"
                  className="mb-1.5 block text-label text-zinc-400"
                >
                  Current password
                </label>
                <input
                  id="current-password"
                  name="current-password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  className="focus-ring w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-body text-zinc-100 outline-none placeholder:text-zinc-400 focus:border-emerald-600"
                />
              </div>

              <div>
                <label htmlFor="new-password" className="mb-1.5 block text-label text-zinc-400">
                  New password
                </label>
                <input
                  id="new-password"
                  name="new-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="focus-ring w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-body text-zinc-100 outline-none placeholder:text-zinc-400 focus:border-emerald-600"
                />
              </div>

              <div>
                <label
                  htmlFor="confirm-password"
                  className="mb-1.5 block text-label text-zinc-400"
                >
                  Confirm new password
                </label>
                <input
                  id="confirm-password"
                  name="confirm-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="focus-ring w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-body text-zinc-100 outline-none placeholder:text-zinc-400 focus:border-emerald-600"
                />
              </div>

              <button
                type="submit"
                disabled={busy}
                className="focus-ring w-full rounded-lg bg-emerald-600 px-4 py-2.5 text-body font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-40"
              >
                {busy ? "Changing password…" : "Change password"}
              </button>
            </form>
          </section>

          <section className="mt-10 rounded-lg border border-red-900 bg-red-950/20 p-5">
            <h2 className="text-headline font-semibold text-red-300">Sign out everywhere</h2>
            <p className="measure mt-2 text-body text-zinc-400">
              Ends every signed-in session for this account, including this one — you&rsquo;ll
              be sent to the sign-in page.
            </p>

            {signOutError && (
              <div className="fade-in mt-4 flex items-start gap-2.5 rounded-lg border border-red-900 bg-red-950/50 px-4 py-3 text-body text-red-300">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-red-500" />
                <span>{signOutError}</span>
              </div>
            )}

            <button
              type="button"
              onClick={handleSignOutAll}
              disabled={signingOutAll}
              className="focus-ring mt-4 rounded-lg border border-red-800 bg-transparent px-4 py-2.5 text-body font-medium text-red-300 transition-colors hover:bg-red-950/50 disabled:opacity-40"
            >
              {signingOutAll ? "Signing out…" : "Sign out everywhere"}
            </button>
          </section>
        </div>
      </main>
    </div>
  );
}
