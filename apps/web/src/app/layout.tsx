import type { Metadata, Viewport } from "next";
import "./globals.css";
import "@/styles/ui.css";
import "@/styles/app.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: {
    default: "ShramAI Inspector",
    template: "%s · ShramAI Inspector",
  },
  description:
    "AI-assisted labour-document inspection platform: evidence-linked screening signals for authorised human review.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main-content">
          Skip to main content
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
