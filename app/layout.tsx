import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Funding Intelligence for Psychology",
  description: "Trova finanziamenti per progetti psicologici con una ricerca semplice e fonti trasparenti.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="it"><body>{children}</body></html>;
}
