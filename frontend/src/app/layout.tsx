import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Property Risk Analyser — Land risk before you buy",
  description:
    "Search any bus stop, street or landmark across India's tier-1 cities and get a "
    + "flood, groundwater and water-supply reading for that exact plot, plus the "
    + "corporation ward it sits in.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
