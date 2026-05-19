import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // The `pg` driver is a server-only dep; mark it external so Next's bundler
  // doesn't try to webpack-trace native bindings into the edge runtime.
  serverExternalPackages: ["pg"],
  poweredByHeader: false,
};

export default config;
