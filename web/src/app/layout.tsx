import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Data Re-cycle",
  description: "Excel -> SDMX metadata extraction, review and export",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="topnav">
          <span className="brand">Data Re-cycle</span>
          <nav>
            <Link href="/upload">Upload</Link>
            <Link href="/processing">Processing</Link>
            <Link href="/review">Metadata Review</Link>
            <Link href="/data-preview">Data Preview</Link>
            <Link href="/export">Export</Link>
            <Link href="/review-metadata">Review Metadata</Link>
            <Link href="/sets">Processed Files</Link>
          </nav>
        </header>
        <main className="page">{children}</main>
      </body>
    </html>
  );
}
