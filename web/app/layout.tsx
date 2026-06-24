import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Volatix Control Board",
  description:
    "Low-latency anomaly detection telemetry for the Volatix-AI engine.",
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
