import type { Metadata } from "next";
import "./globals.css";
import "./variant-c.css";
import "./vector.css";
import "./landing.css";
import "./auth.css";
export const metadata: Metadata = {
  title: {
    default: "ФСП Вектор — компетенции, которым доверяют",
    template: "%s · ФСП Вектор",
  },
  description:
    "Паспорт подтверждённых компетенций и персональные предложения от ИТ-команд.",
  robots: { index: false, follow: false },
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru" data-scroll-behavior="smooth">
      <head>
        <link
          rel="preload"
          href="/fonts/inter-variable.woff2"
          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
