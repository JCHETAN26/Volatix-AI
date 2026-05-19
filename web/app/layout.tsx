import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "ChainGuard Control Board",
  description:
    "Low-latency anomaly detection telemetry for the ChainGuard-Core engine.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg bg-grid">{children}</body>
    </html>
  );
}
