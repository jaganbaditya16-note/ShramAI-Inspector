import Link from "next/link";

export function StatCard({
  label,
  value,
  hint,
  href,
}: {
  label: string;
  value: string;
  hint?: string;
  href?: string;
}) {
  const body = (
    <>
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      {hint ? <p className="stat-hint">{hint}</p> : null}
    </>
  );
  if (href) {
    return (
      <Link className="stat-card" href={href} style={{ textDecoration: "none", color: "inherit" }}>
        {body}
      </Link>
    );
  }
  return <div className="stat-card">{body}</div>;
}
