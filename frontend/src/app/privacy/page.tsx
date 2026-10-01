import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy — TerrisIQ",
  description:
    "How TerrisIQ handles data: you enter a property address, we send only that address "
    + "to our risk API to compute a score. No page access, no tracking, no identifiers.",
};

const UPDATED = "1 October 2026";
const CONTACT = "jitheshkhannaofficial@gmail.com";

export default function PrivacyPage() {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        overflowY: "auto",
        background: "var(--plane)",
        color: "var(--ink)",
        WebkitOverflowScrolling: "touch",
      }}
    >
      <main
        style={{
          maxWidth: 720,
          margin: "0 auto",
          padding: "56px 20px 96px",
          lineHeight: 1.6,
        }}
      >
        <p
          style={{
            fontSize: 12,
            fontWeight: 600,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--ink-muted)",
            margin: 0,
          }}
        >
          TerrisIQ
        </p>
        <h1 style={{ fontSize: 34, fontWeight: 700, letterSpacing: "-0.02em", margin: "8px 0 6px" }}>
          Privacy Policy
        </h1>
        <p style={{ color: "var(--ink-muted)", margin: "0 0 32px", fontSize: 14 }}>
          Last updated: {UPDATED}
        </p>

        <p>
          TerrisIQ helps you evaluate a property&rsquo;s environmental risk &mdash; flood,
          groundwater and water scarcity &mdash; for an address you choose to enter. This
          policy covers both the TerrisIQ browser extension and the TerrisIQ web app, and
          describes exactly what each does and does not do with data.
        </p>

        <Section title="What the extension collects">
          <p>
            <strong>Only the location text you type into the search box.</strong> As you type,
            that text is sent to the TerrisIQ API (<code>chennai-terra-risk.vercel.app</code>)
            to fetch matching address suggestions. When you pick one, the extension sends its
            coordinates to the same API to compute the risk score. Nothing else is sent, and
            nothing is sent until you start typing in the box.
          </p>
          <p>
            The extension does <strong>not</strong> use any account, login, cookie, or
            per-user / per-device identifier. It does not fingerprint or track you.
          </p>
        </Section>

        <Section title="What the extension does NOT do">
          <ul style={ulStyle}>
            <li>It does <strong>not</strong> read, scan, or access the web page or tab you are viewing.</li>
            <li>It does <strong>not</strong> run on Google Maps, NoBroker, 99acres, MagicBricks, Housing.com, or any other website.</li>
            <li>It has <strong>no</strong> content scripts and <strong>no</strong> access to any site other than its own API.</li>
            <li>It does <strong>not</strong> read your browsing history, bookmarks, cookies, or form fields.</li>
            <li>It does <strong>not</strong> run anything in the background &mdash; it acts only when you click.</li>
            <li>It contains <strong>no</strong> analytics, tracking, or advertising code.</li>
          </ul>
        </Section>

        <Section title="Permissions the extension requests">
          <ul style={ulStyle}>
            <li>
              <strong>storage</strong> &mdash; to briefly cache a risk result on your own device
              (about 30 minutes) so re-checking the same address is instant. Nothing in this
              cache leaves your device.
            </li>
            <li>
              <strong>Access to the TerrisIQ API host only</strong> &mdash; so the extension can
              send your address to our risk service and receive the score. This is the single
              host the extension can contact.
            </li>
          </ul>
        </Section>

        <Section title="Third-party processing (be transparent)">
          <p>
            To turn an address into coordinates, the TerrisIQ API uses open geocoding services
            &mdash; <strong>Photon (by Komoot)</strong> and <strong>Nominatim
            (OpenStreetMap)</strong>. The address text you enter is sent to these services for
            that lookup. We do not send them any identifier.
          </p>
          <p>
            Our services are hosted on <strong>Vercel</strong>. As with any website, Vercel&rsquo;s
            platform may record standard request metadata (such as IP address and timestamp) in
            transient infrastructure logs. We do not use this for tracking or profiling.
          </p>
        </Section>

        <Section title="What we store">
          <ul style={ulStyle}>
            <li>
              The TerrisIQ application code does <strong>not</strong> write your address to a
              database or retain it after computing your score &mdash; it is processed to produce
              the result and not kept.
            </li>
            <li>
              A short-lived risk-result cache lives <strong>locally in your browser</strong> and
              is cleared when you remove the extension.
            </li>
          </ul>
        </Section>

        <Section title="Data sharing &amp; sale">
          <p>
            We do <strong>not</strong> sell your data, share it for advertising, or use it to
            train AI models. The only external parties that receive the address are the geocoding
            services named above, purely to resolve its location.
          </p>
        </Section>

        <Section title="The web app">
          <p>
            The TerrisIQ web app works the same way: you enter or select a location and receive a
            risk analysis. When the extension opens the full report, it passes the coordinates of
            the location you analyzed in the link &mdash; no personal data is included.
          </p>
        </Section>

        <Section title="Children">
          <p>TerrisIQ is not directed to children under 13 and collects no personal information.</p>
        </Section>

        <Section title="Changes">
          <p>
            We may update this policy; material changes will be reflected here and in the
            extension listing, with the date above.
          </p>
        </Section>

        <Section title="Contact">
          <p>
            Questions or requests:{" "}
            <a href={`mailto:${CONTACT}`} style={{ color: "var(--good-text)" }}>{CONTACT}</a>.
          </p>
        </Section>
      </main>
    </div>
  );
}

const ulStyle: React.CSSProperties = { paddingLeft: 22, margin: 0, display: "grid", gap: 8 };

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginTop: 32 }}>
      <h2 style={{ fontSize: 20, fontWeight: 700, letterSpacing: "-0.01em", margin: "0 0 10px" }}>
        {title}
      </h2>
      <div style={{ display: "grid", gap: 12 }}>{children}</div>
    </section>
  );
}
