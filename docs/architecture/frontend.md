# Frontend Architecture

Next.js 16 App Router, TypeScript strict, React 19.

## Structure

```
apps/web/src/
  app/
    layout.tsx            root: metadata, providers, skip link
    providers.tsx         TanStack Query + Toast providers
    login/page.tsx        session login (required mode)
    (app)/                authenticated shell (sidebar + topbar + guard)
      dashboard/page.tsx  org aggregates + recent activity
      cases/page.tsx      list + filters + create dialog
      cases/[caseId]/     layout (header + section tabs)
        page.tsx          overview: upload panel, top findings, score, activity
        findings/page.tsx filters + review workflow
        documents/page.tsx  status table, polling, reprocess, download
        report/page.tsx   scorecard snapshot + provenance + JSON download
        audit/page.tsx    full trail
      settings/page.tsx   environment + AI governance notes
  components/
    ui/        primitives (button, badge, dialog, toast, feedback, score ring, icons)
    app/       feature components (shell, finding card, upload panel, timeline…)
    motion.tsx reduced-motion-aware transitions
  hooks/       useSession/useHealth
  lib/         typed API client, contract types, formatting, query keys
  styles/      ui.css (primitives) + app.css (features); tokens in globals.css
```

## Principles

- **No fake fallbacks**: if the API fails, UI shows an explicit error state with a
  retry; optimistic updates always roll back via mutation error paths. The old
  "browser fallback report" pattern was removed deliberately.
- **Server state via TanStack Query**: polling while documents are queued/processing,
  cache invalidation after mutations (findings → dashboard → report).
- **Same-origin API**: the browser only calls `/api/v1/...`; Next.js server rewrites
  proxy to the API (build-time `API_ORIGIN`), keeping cookies first-party.
- **Accessibility**: semantic landmarks, labelled controls, `aria-current` tabs,
  focus-trapped dialog with Escape + restore, `role="status"` live regions,
  visible focus rings, `prefers-reduced-motion` gating for every Framer Motion
  transition (pages, dialogs, toasts, score ring, finding reveals).
- **Honest AI framing**: badges distinguish `Rule check` vs `AI-assisted`; evidence
  boxes show quote + page + char anchors or an explicit absence note; confidence is
  a labelled bar, never a verdict.
