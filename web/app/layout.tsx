import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Chess vs. LLM",
  description: "Play chess against an LLM, with games stored for rewind and analysis.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="container">
          <header style={{ marginBottom: 20 }}>
            <Link href="/"><strong>♞ Chess vs. LLM</strong></Link>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
