import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "revvec, airgapped industrial RAG, on-device.",
  description:
    "On-prem retrieval augmented generation built on Actian VectorAI DB. Zero cloud. Compliant by construction with CMMC, ITAR, 21 CFR Part 11, NIS2.",
  metadataBase: new URL("https://revvec.dev"),
  openGraph: {
    title: "revvec, airgapped industrial RAG",
    description:
      "Your SOPs, sensor streams, and mission docs cannot touch a cloud LLM. revvec is the on-device answer.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        <div className="grain" />
        {children}
      </body>
    </html>
  );
}
