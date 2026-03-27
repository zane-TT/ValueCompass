import type { Metadata } from "next";
import { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Equity Research Agent",
  description: "Financial quality, valuation, and memo generation for stock research."
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
