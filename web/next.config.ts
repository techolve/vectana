import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// Exported as static files and served by the FastAPI app (same origin).
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  reactCompiler: true,
  images: { unoptimized: true },
  // In `next dev`, forward API calls to a locally running FastAPI.
  ...(process.env.NODE_ENV === "development"
    ? {
        async rewrites() {
          return [{ source: "/api/:path*", destination: "http://localhost:8000/api/:path*" }];
        },
      }
    : {}),
};

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

export default withNextIntl(nextConfig);
