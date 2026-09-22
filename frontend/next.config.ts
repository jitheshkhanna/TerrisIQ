import type { NextConfig } from "next";

// Where /api/* is proxied to. Rewrites are baked at build time, so this must be a
// build-time value.
//
// The fallback is per-environment rather than a single default: a production build with
// API_ORIGIN unset previously fell back to 127.0.0.1 and shipped a site whose every API
// call 404'd, with nothing in the build log to say so. Defaulting production to the
// deployed API makes that failure impossible; local dev still points at localhost.
const PRODUCTION_API = "https://chennai-terra-risk-api.vercel.app";
const API_ORIGIN =
  process.env.API_ORIGIN ??
  (process.env.NODE_ENV === "production" ? PRODUCTION_API : "http://127.0.0.1:8000");

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
