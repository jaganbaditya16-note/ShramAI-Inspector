"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { api, errorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ message: string; requestId?: string } | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.post("/auth/login", { email: email.trim(), password });
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setError({
        message: errorMessage(err),
        requestId: undefined,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <span className="brand-mark" aria-hidden>
          S
        </span>
        <h1>Sign in to ShramAI Inspector</h1>
        <p className="auth-sub">
          Authorised inspectors only. All review actions are audited.
        </p>
        {error ? (
          <div style={{ marginBottom: 14 }}>
            <InlineError message={error.message} />
          </div>
        ) : null}
        <form className="auth-form" onSubmit={(event) => void onSubmit(event)}>
          <div>
            <label className="field-label" htmlFor="login-email">
              Work email
            </label>
            <input
              id="login-email"
              className="input"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div>
            <label className="field-label" htmlFor="login-password">
              Password
            </label>
            <input
              id="login-password"
              className="input"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <Button variant="accent" type="submit" loading={submitting}>
            Sign in
          </Button>
        </form>
        <p className="demo-note">
          This deployment may run in <strong>demo mode</strong> (no login required), in which
          case you will be redirected automatically. Demo mode uses synthetic data only.
        </p>
      </div>
    </div>
  );
}
