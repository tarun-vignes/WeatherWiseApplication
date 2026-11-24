import type { NextConfig } from "next";

// Public variables are embedded during `next build`; fail early if Render is
// missing the backend URL instead of shipping a localhost address to visitors.
if (process.env.RENDER === "true") {
  const value = process.env.NEXT_PUBLIC_API_URL?.trim();
  let url: URL;
  try {
    if (!value) throw new Error("missing URL");
    url = new URL(value);
  } catch {
    throw new Error("Set NEXT_PUBLIC_API_URL to the public HTTPS backend URL before building on Render.");
  }
  if (url.protocol !== "https:" || ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname) || url.username || url.password || url.pathname !== "/" || url.search || url.hash) {
    throw new Error("NEXT_PUBLIC_API_URL must be a public HTTPS origin without credentials, a path, query, or fragment.");
  }
}

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
};

export default nextConfig;
