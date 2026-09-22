import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy — Terrisiq",
  description:
    "How the Terrisiq browser extension handles data: it reads only the location of "
    + "the page you actively score, sends it to the risk API, and collects no personal "
    + "data, browsing history, or tracking profile.",
};

const UPDATED = "19 September 2026";
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
          Terrisiq
        </p>
        <h1 style={{ fontSize: 34, fontWeight: 700, letterSpacing: "-0.02em", margin: "8px 0 6px" }}>
          Privacy Policy
        </h1>
        <p style={{ color: "var(--ink-muted)", margin: "0 0 32px", fontSize: 14 }}>
          Last updated: {UPDATED}
        </p>

        <p>
          Terrisiq (&ldquo;the extension&rdquo;) helps you see environmental risk &mdash; flood,
          groundwater contamination, and water scarcity &mdash; for a property or map location on
          supported websites. This policy explains exactly what the extension does and does not do
          with data.
        </p>

        <Section title="What we collect">
          <p>
            <strong>Only the location of the page you are actively viewing, and only when you ask
            for a score.</strong> When you click the Terrisiq badge on a supported page, the
            extension reads the property&rsquo;s location from that page &mdash; either its
            coordinates (latitude/longitude) or a short address/locality string &mdash; and sends it
            to the Terrisiq risk API (<code>https://chennai-terra-risk.vercel.app</code>) to
            calculate and return a risk score.
          </p>
          <p>
            A random, anonymous installation identifier is generated on first run and stored
            locally. It is sent with API requests only to apply fair-use rate limits. It is not
            linked to your identity, your Google account, or any personal profile.
          </p>
        </Section>

        <Section title="What we do NOT collect">
          <ul style={ulStyle}>
            <li>We do <strong>not</strong> collect your name, email, phone number, or any personal identifier.</li>
            <li>We do <strong>not</strong> read, store, or transmit your browsing history.</li>
            <li>We do <strong>not</strong> track you across sites or build an advertising/behavioural profile.</li>
            <li>We do <strong>not</strong> access passwords, form fields, cookies, or saved autofill data.</li>
            <li>We do <strong>not</strong> read pages on sites you have not explicitly enabled.</li>
            <li>We do <strong>not</strong> sell or share data with third parties for advertising.</li>
          </ul>
        </Section>

        <Section title="Permissions and why">
          <ul style={ulStyle}>
            <li>
              <strong>Site access (per-site, optional):</strong> granted only for the specific sites
              you turn on (e.g. Google Maps, NoBroker). It lets the extension read the property
              location on those sites to show a score. You can revoke any site at any time from the
              popup or <code>chrome://extensions</code>.
            </li>
            <li>
              <strong>activeTab / scripting:</strong> to display the badge on the current tab,
              including the one-off &ldquo;Try on the current tab&rdquo; action.
            </li>
            <li>
              <strong>storage:</strong> to remember your enabled sites, cache recent scores briefly
              on your device (about 30 minutes), and hold the anonymous rate-limit identifier.
            </li>
            <li>
              <strong>API host access:</strong> to send the viewed location to the risk API and
              receive the score.
            </li>
          </ul>
        </Section>

        <Section title="Data storage and retention">
          <ul style={ulStyle}>
            <li>
              Enabled-site settings, the anonymous identifier, and a short-lived score cache are
              stored <strong>locally in your browser</strong>. Removing the extension deletes them.
            </li>
            <li>
              Location lookups sent to the API may be processed and cached server-side transiently
              to return and speed up results. They are not tied to your identity.
            </li>
          </ul>
        </Section>

        <Section title="Data sharing">
          <p>
            Location coordinates/addresses you request a score for are sent to the Terrisiq API to
            produce the score. No data is sent to any other third party.
          </p>
        </Section>

        <Section title="Children">
          <p>
            Terrisiq is not directed to children under 13 and collects no personal information.
          </p>
        </Section>

        <Section title="Changes">
          <p>
            We may update this policy; material changes will be reflected in the extension listing
            and this document&rsquo;s date.
          </p>
        </Section>

        <Section title="Contact">
          <p>
            Questions or requests: <a href={`mailto:${CONTACT}`} style={{ color: "var(--good-text)" }}>{CONTACT}</a>.
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
