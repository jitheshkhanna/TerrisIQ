"use client";

import { useEffect, useRef, useState } from "react";
import {
  askChat,
  isShortMapLink,
  parseLocationInput,
  riskContext,
  type ChatTurn,
  type RiskResult,
} from "@/lib/api";

interface Props {
  result: RiskResult | null;
  /** Let the user drop a Google Maps link straight into the chat to score it. */
  onLocation: (lat: number, lng: number, label: string) => void;
}

type Message = { role: "user" | "assistant" | "note"; text: string };

const SUGGESTIONS = [
  "Explain the biggest risk here",
  "How much FSI & height can I build here?",
  "Is the water situation a problem?",
  "What should I check before buying?",
];

export default function ChatPanel({ result, onLocation }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  const send = async (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;

    // A pasted Maps link or coordinate scores that spot instead of asking a question.
    const pinned = parseLocationInput(text);
    if (pinned) {
      onLocation(pinned.latitude, pinned.longitude, pinned.label);
      setInput("");
      setMessages((m) => [
        ...m,
        { role: "note", text: `Scoring the pinned location (${pinned.label})…` },
      ]);
      return;
    }
    if (isShortMapLink(text)) {
      setInput("");
      setMessages((m) => [
        ...m,
        {
          role: "note",
          text: "That's a short share link. Open it, then paste the full google.com/maps URL here.",
        },
      ]);
      return;
    }

    setInput("");
    const nextMessages: Message[] = [...messages, { role: "user", text }];
    setMessages(nextMessages);
    setBusy(true);

    const history: ChatTurn[] = nextMessages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .slice(0, -1)
      .map((m) => ({ role: m.role === "assistant" ? "model" : "user", text: m.text }));

    try {
      const answer = await askChat(text, result ? riskContext(result) : null, history);
      setMessages((m) => [...m, { role: "assistant", text: answer }]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        {
          role: "note",
          text:
            err instanceof Error && /busy/i.test(err.message)
              ? "The assistant is busy for a second. Try again."
              : "Couldn't reach the assistant. Try again in a moment.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card mt-3 flex flex-col p-4">
      <div className="flex items-center gap-2 px-1">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--plane)]">
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 text-[var(--ink-2)]" fill="none" aria-hidden>
            <path d="M2 3.5h12v7H6l-3 2.5v-2.5H2v-7Z" stroke="currentColor" strokeWidth="1.3"
                  strokeLinejoin="round" />
          </svg>
        </span>
        <h2 className="text-[15px] font-semibold text-[var(--ink)]">Ask about this place</h2>
      </div>

      <div
        ref={scroller}
        className="quiet-scroll mt-3 flex max-h-[38vh] flex-col gap-2.5 overflow-y-auto px-1"
      >
        {messages.length === 0 && (
          <p className="py-1 text-[14px] leading-relaxed text-[var(--ink-muted)]">
            {result
              ? "Ask anything about this location's risk and buildability."
              : "Search a place, drop a pin, or paste a Google Maps link, then ask me anything about its risk."}
          </p>
        )}

        {messages.map((m, i) =>
          m.role === "note" ? (
            <p key={i} className="px-1 text-[13px] italic text-[var(--ink-muted)]">
              {m.text}
            </p>
          ) : (
            <div
              key={i}
              className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
            >
              <span
                className={
                  m.role === "user"
                    ? "max-w-[85%] rounded-2xl rounded-br-sm bg-[var(--ink)] px-3.5 py-2 text-[14px] leading-relaxed text-[var(--surface)]"
                    : "max-w-[90%] whitespace-pre-wrap rounded-2xl rounded-bl-sm bg-[var(--plane)] px-3.5 py-2 text-[14px] leading-relaxed text-[var(--ink)]"
                }
              >
                {m.text}
              </span>
            </div>
          ),
        )}

        {busy && (
          <div className="flex justify-start">
            <span className="rounded-2xl rounded-bl-sm bg-[var(--plane)] px-3.5 py-2.5">
              <span className="flex gap-1">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--ink-muted)] [animation-delay:-0.3s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--ink-muted)] [animation-delay:-0.15s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--ink-muted)]" />
              </span>
            </span>
          </div>
        )}
      </div>

      {result && messages.length === 0 && (
        <div className="mt-3 flex flex-wrap gap-2 px-1">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => send(s)}
              className="rounded-full border border-[var(--edge)] px-3 py-1.5 text-[13px]
                         text-[var(--ink-2)] transition hover:border-[var(--ink)] hover:text-[var(--ink)]"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="mt-3 flex items-center gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this place…"
          aria-label="Ask about this location"
          className="min-h-[46px] flex-1 rounded-xl border border-[var(--hairline)] bg-[var(--surface)]
                     px-3.5 text-[15px] text-[var(--ink)] placeholder:text-[var(--ink-muted)]
                     focus:border-[var(--edge)] focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          aria-label="Send"
          className="flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-xl
                     bg-[var(--accent)] text-[var(--accent-ink)] transition
                     hover:bg-[var(--accent-strong)] disabled:opacity-40"
        >
          <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" aria-hidden>
            <path d="M2 8h11M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.6"
                  strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </form>
    </div>
  );
}
