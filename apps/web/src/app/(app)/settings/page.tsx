"use client";

import { useHealth, useSession } from "@/hooks/use-session";
import { PageHeader } from "@/components/app/page-header";
import { PageFade } from "@/components/motion";
import { Card } from "@/components/ui/card";
import { formatDateTime } from "@/lib/format";

export default function SettingsPage() {
  const { data: health } = useHealth();
  const { user } = useSession();

  return (
    <PageFade>
      <PageHeader
        kicker="Workspace"
        title="Settings & status"
        description="Deployment status, AI configuration and governance notes for this environment."
      />
      <div className="stack" style={{ maxWidth: 720 }}>
        <Card title="Environment">
          <div style={{ display: "grid", gap: 10 }}>
            <Row label="Environment" value={health?.app_env ?? "—"} />
            <Row label="API version" value={health?.version ?? "—"} />
            <Row
              label="Authentication"
              value={
                health?.auth_mode === "required"
                  ? "Sessions required (organisational users)"
                  : "Demo mode (synthetic data only)"
              }
            />
            <Row
              label="AI analysis"
              value={
                health?.ai.configured
                  ? `Enabled · provider ${health.ai.provider}`
                  : "Disabled · deterministic rules only"
              }
            />
            <Row label="Session started" value={formatDateTime(new Date().toISOString())} mono />
          </div>
        </Card>

        <Card title="AI governance">
          <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 8, fontSize: 13, lineHeight: 1.55, color: "var(--ink-600)" }}>
            <li>
              Findings are <strong>screening signals for authorised human review</strong> — never
              automatic legal conclusions, penalties or enforcement decisions.
            </li>
            <li>
              AI findings must cite evidence <strong>verbatim from the document text</strong>;
              quotes that cannot be located are rejected automatically and counted on the model
              run record.
            </li>
            <li>
              Text inside uploaded documents is treated as <strong>untrusted data</strong> —
              instructions inside documents cannot override system behaviour.
            </li>
            <li>
              Every model run is recorded with provider, model, prompt version and grounding
              statistics in the case report provenance section.
            </li>
          </ul>
        </Card>

        {user ? (
          <Card title="Your session">
            <div style={{ display: "grid", gap: 10 }}>
              <Row label="Name" value={user.name} />
              <Row label="Email" value={user.email} mono />
              <Row label="Role" value={user.role} />
              {user.is_demo ? (
                <p className="text-small text-muted">
                  Demo principals share one synthetic workspace. Configure
                  <code className="mono"> AUTH_MODE=required</code> with a bootstrap admin to
                  enable per-user sessions.
                </p>
              ) : null}
            </div>
          </Card>
        ) : null}
      </div>
    </PageFade>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 13 }}>
      <span className="text-muted">{label}</span>
      <span className={`text-strong ${mono ? "mono" : ""}`}>{value}</span>
    </div>
  );
}
