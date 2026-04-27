/** @type {import('next').NextConfig} */
const adminApiBase = process.env.NEXT_PUBLIC_ADMIN_API_BASE ?? "http://localhost:8080";
const isDev = process.env.NODE_ENV !== "production";
const scriptSrc = ["script-src", "'self'", "'unsafe-inline'", ...(isDev ? ["'unsafe-eval'"] : [])];

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: "standalone",
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              `connect-src 'self' ${adminApiBase}`,
              scriptSrc.join(" "),
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: blob:",
              "font-src 'self'",
              "frame-ancestors 'none'",
            ].join("; "),
          },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
