# Frontend and Backend Integration

## Local development

Frontend:
- URL: http://localhost:3000
- Environment: NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1

Backend:
- URL: http://localhost:8000
- Health: GET /api/v1/health
- OpenAPI: http://localhost:8000/api/docs

## Request flow

1. Browser loads the Next.js application.
2. The frontend reads NEXT_PUBLIC_API_BASE_URL.
3. The dashboard calls /health and /cases.
4. FastAPI validates response models.
5. The API returns JSON.
6. The frontend renders the server state.

## Production direction

Use a same-origin reverse proxy or trusted allowlist rather than wildcard CORS. Authentication and authorization belong to the backend. Uploads should use controlled object-storage URLs rather than exposing filesystem paths.

## Error handling

Frontend should distinguish:
- network unavailable
- authentication/authorization failure
- validation error
- processing failure
- upstream AI unavailable

The UI should provide a request ID when available and never expose stack traces to end users.
