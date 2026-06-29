import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Chess vs. LLM",
  description: "A vendor-neutral full-stack reference: chess engine, LLM opponent, observability.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="container">
          <header style={{ marginBottom: 20 }}>
            <Link href="/"><strong>♞ Chess vs. LLM</strong></Link>
            <span className="muted"> — reference building block</span>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
