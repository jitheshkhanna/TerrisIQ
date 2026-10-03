import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TerrisIQ · Property risk before you buy",
  description:
    "TerrisIQ shows the flood, groundwater and water-scarcity risk of any address across "
    + "India's tier-1 cities. The risk IQ every listing is missing.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
