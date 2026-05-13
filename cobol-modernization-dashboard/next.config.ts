import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Pin app root so Turbopack does not pick a parent folder that has another package-lock.json
// (e.g. C:\Users\...\), which breaks `@/*` imports such as `@/lib/demo`.
const appRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  turbopack: {
    root: appRoot,
  },
};

export default nextConfig;
