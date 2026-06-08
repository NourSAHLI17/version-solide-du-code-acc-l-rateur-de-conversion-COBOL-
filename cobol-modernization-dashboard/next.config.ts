import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Pin app root so Turbopack does not pick a parent folder that has another package-lock.json
// (e.g. C:\Users\...\), which breaks `@/*` imports such as `@/lib/demo`.
const appRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  // Allow HMR WebSocket when the app is opened via 127.0.0.1 while the dev server uses localhost (or vice versa).
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  turbopack: {
    root: appRoot,
  },
};

export default nextConfig;
