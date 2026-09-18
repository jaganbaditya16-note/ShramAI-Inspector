# Web

Next.js 16 inspector dashboard for the ShramAI Inspector prototype.

Implemented screens:
- Overview and screening score
- Findings review with accept/dismiss
- Document register
- Audit trail
- Case creation
- PDF/PNG/JPEG upload with drag-and-drop
- Scorecard generation and JSON export

The browser calls the FastAPI API through `NEXT_PUBLIC_API_BASE_URL`, defaulting to same-origin `/api/v1` for the Vercel deployment.

The UI is intentionally assistive: findings are screening signals and the final compliance determination remains with the authorized human reviewer.
