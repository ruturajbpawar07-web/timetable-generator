import type { NextConfig } from "next";

const API = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone", // self-contained server for the Docker image
  // Browser calls /api/*; Next proxies to FastAPI, so no CORS setup is needed.
  rewrites: async () => [{ source: "/api/:path*", destination: `${API}/:path*` }],
  experimental: { proxyTimeout: 120_000 }, // solver runs can take ~20s
};

export default nextConfig;
