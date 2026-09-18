import type { NextConfig } from "next";

const API_ORIGIN = process.env.API_ORIGIN || "http://127.0.0.1:8000";

/**
 * The browser only ever calls same-origin `/api/v1/...`. The Next.js server
 * proxies those paths to the API (container-local), which keeps cookies
 * first-party in every deployment (docker, preview, Vercel rewrites).
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${API_ORIGIN}/api/v1/:path*` },
      { source: "/api/openapi.json", destination: `${API_ORIGIN}/api/openapi.json` },
      { source: "/api/docs", destination: `${API_ORIGIN}/api/docs` },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
