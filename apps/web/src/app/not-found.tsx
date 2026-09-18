import Link from "next/link";

export default function NotFound() {
  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <div style={{ textAlign: "center", maxWidth: 440 }}>
        <p className="kicker">404</p>
        <h1 style={{ fontSize: 20, letterSpacing: "-0.02em" }}>Page not found</h1>
        <p style={{ color: "var(--ink-500)", fontSize: 13, marginTop: 8 }}>
          The page you requested does not exist or has moved.
        </p>
        <Link className="btn btn-primary" href="/dashboard" style={{ display: "inline-flex", marginTop: 18 }}>
          Go to dashboard
        </Link>
      </div>
    </main>
  );
}
