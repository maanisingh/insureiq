import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title:       "InsureIQ — AI-Powered Intelligence for Insurance Professionals",
  description: "Price risks, underwrite decisions, and draft policies — all in one AI conversation with 5 specialist agents.",
  metadataBase: new URL("https://ai.cipherx.co.uk"),
  openGraph: {
    title:       "InsureIQ — AI Insurance Intelligence",
    description: "5 specialist AI agents for pricing, underwriting, policy drafting, RAG search, and research. Zero hallucination. Sources cited.",
    url:         "https://ai.cipherx.co.uk",
    siteName:    "InsureIQ",
    type:        "website",
  },
  twitter: {
    card:        "summary_large_image",
    title:       "InsureIQ — AI Insurance Intelligence",
    description: "Price risks, underwrite decisions, and draft policies with AI.",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
