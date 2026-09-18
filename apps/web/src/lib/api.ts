/** Typed API client with consistent error surfacing (no silent fallbacks). */

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId: string;

  constructor(status: number, code: string, message: string, requestId: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

interface ErrorBody {
  error?: { code?: string; message?: string; request_id?: string };
  detail?: unknown;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ErrorBody = {};
  try {
    body = (await response.json()) as ErrorBody;
  } catch {
    // non-JSON error body (proxy/network layer)
  }
  if (body.error) {
    return new ApiError(
      response.status,
      body.error.code ?? "http_error",
      body.error.message ?? "Request failed.",
      body.error.request_id ?? "unknown",
    );
  }
  return new ApiError(
    response.status,
    "http_error",
    `Request failed (${response.status}).`,
    "unknown",
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    credentials: "same-origin",
    ...init,
    headers: {
      ...(init?.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return "Cannot reach the API. Check your connection and retry.";
  }
  return "An unexpected error occurred.";
}

export function errorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.code : null;
}
