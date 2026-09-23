import type { NextConfig } from "next";

/**
 * ARTIFACT_EXPORT=1 produces a fully static build in `out/` with relative asset
 * paths, for previewing the site on a host that serves it from a sub-path.
 * Normal builds and deploys are unaffected.
 */
const artifactExport = process.env.ARTIFACT_EXPORT === "1";

const nextConfig: NextConfig = {
  ...(artifactExport
    ? {
        output: "export" as const,
        assetPrefix: "./site",
        images: { unoptimized: true },
      }
    : {}),
};

export default nextConfig;
