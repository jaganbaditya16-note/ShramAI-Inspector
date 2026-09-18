import { NextResponse, type NextRequest } from "next/server";

/**
 * Runtime API proxy.
 *
 * `next start` serves rewrites from the build-time manifest, so a runtime
 * API_ORIGIN env would otherwise be silently ignored (browser E2E caught
 * this). This middleware proxies the same-origin API paths to API_ORIGIN
 * when the variable is set at RUNTIME; when it is not set the request falls
 * through to the build-time rewrites (Docker build ARG / Vercel config),
 * keeping every existing deployment behaviour unchanged.
 */
export function middleware(request: NextRequest) {
  const origin = process.env.API_ORIGIN?.trim();
  if (!origin) {
    return NextResponse.next();
  }
  const path = `${request.nextUrl.pathname}${request.nextUrl.search}`;
  return NextResponse.rewrite(new URL(path, origin));
}

export const config = {
  runtime: "nodejs",
  matcher: ["/api/v1/:path*", "/api/openapi.json", "/api/docs"],
};
