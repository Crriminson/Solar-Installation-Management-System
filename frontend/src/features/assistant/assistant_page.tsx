/*
  The staff assistant (F21).

  For the small doubts that used to be a phone call: what size cable,
  what the subsidy is, what a fault means. It answers from reviewed notes
  and shows where each answer came from and when that was checked, so a
  figure can be judged rather than trusted.

  It has no customer, order or cost records, and the screen says so.
*/

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import Button from "../../components/Button";
import PageHeader from "../../components/PageHeader";
import { ErrorMessage } from "../../components/StateMessage";
import { ICON_SIZE, OpenRecordIcon, SendIcon, StopIcon, WarningIcon } from "../../design/icons";
import { formatDate } from "../../lib/format";
import { hasRole, useStaffUser } from "../auth/session";
import { fetchStatus, type Source } from "./api";
import { useChat, type ChatMessage } from "./use_chat";
import styles from "./assistant.module.css";

const MAX_QUESTION_CHARS = 1000;

const STARTERS: Record<string, readonly string[]> = {
  technician: [
    "How do I measure a cable run?",
    "Voltage drop on 4 mm², 20 m one way, 13 A, 350 V string?",
    "The inverter shows an isolation fault",
    "How do I shut a system down safely?",
  ],
  sales: [
    "What is the central subsidy for 3 kW?",
    "Will solar work during a power cut?",
    "What documents does the customer need?",
    "How much advance does a customer pay?",
  ],
  director: [
    "How is the rooftop market doing this year?",
    "When does PM Surya Ghar end?",
    "What is changing with the ALMM rules?",
    "How do subsidies appear on our quotations?",
  ],
};

const GENERAL_STARTERS = [
  "When does the warranty start?",
  "When can a ticket be closed?",
  "What does DCR mean?",
  "How many units does 3 kW generate a day?",
];

function startersFor(user: ReturnType<typeof useStaffUser>) {
  const role = Object.keys(STARTERS).find((name) => hasRole(user, name));
  return role ? STARTERS[role] : GENERAL_STARTERS;
}

/* A model trained on web pages sometimes adds bold markers anyway. */
function plainText(text: string) {
  return text.replace(/\*\*/g, "");
}

export default function AssistantPage() {
  const user = useStaffUser();
  const status = useQuery({ queryKey: ["assistant", "status"], queryFn: fetchStatus });
  const { messages, asking, ask, stop, clear } = useChat(user.id);
  const [question, setQuestion] = useState("");
  const latest = useRef<HTMLDivElement>(null);

  const lastText = messages.at(-1)?.text;
  useEffect(() => {
    latest.current?.scrollIntoView({ block: "end" });
  }, [messages.length, lastText]);

  const ready = status.data?.ready ?? false;

  function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || asking || !ready) return;
    setQuestion("");
    void ask(trimmed);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    send(question);
  }

  /* Enter sends, as in any chat. Shift+Enter is still a new line. */
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send(question);
    }
  }

  return <>
    <PageHeader
      title="Assistant"
      subtitle="Quick answers on subsidies, wiring, faults, the solar market and how we work."
      actions={messages.length > 0 && !asking
        ? <Button variant="quiet" onClick={clear}>New conversation</Button>
        : undefined}
    />

    {status.isError && <ErrorMessage error={status.error} onRetry={status.refetch} />}
    {status.data && !ready && (
      <p className={styles.problem} role="alert">
        <WarningIcon size={ICON_SIZE.control} aria-hidden />
        {status.data.problem}
      </p>
    )}

    <div className={styles.chat}>
      {messages.length === 0 && ready && (
        <div className={styles.starters}>
          <p className={styles.muted}>Try one of these, or ask your own.</p>
          <ul>
            {startersFor(user).map((starter) => (
              <li key={starter}>
                <button type="button" className={styles.starter} onClick={() => send(starter)}>
                  {starter}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {messages.map((message) => (
        <Message key={message.id} message={message} />
      ))}
      <div ref={latest} className={styles.end} />
    </div>

    <form className={styles.composer} onSubmit={handleSubmit}>
      <textarea
        className={styles.input}
        aria-label="Your question"
        placeholder="Ask a question"
        rows={2}
        maxLength={MAX_QUESTION_CHARS}
        value={question}
        disabled={!ready}
        onChange={(event) => setQuestion(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      {asking
        ? <Button icon={<StopIcon size={ICON_SIZE.control} aria-hidden />} onClick={stop}>
            Stop
          </Button>
        : <Button type="submit" variant="primary" disabled={!ready || !question.trim()}
            icon={<SendIcon size={ICON_SIZE.control} aria-hidden />}>
            Ask
          </Button>}
    </form>
    <p className={styles.caption}>
      It has no customer, order, price or cost records. It can be wrong: check the manual
      before live electrical work, and the quotation before telling a customer a figure.
    </p>
  </>;
}

function Message({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return <p className={styles.question}>{message.text}</p>;
  }

  const waiting = !message.text;

  return (
    <div className={`${styles.answer} ${message.failed ? styles.failed : ""}`}>
      {waiting
        ? <p className={styles.waiting} role="status">Reading the notes…</p>
        : <p className={styles.answerText} aria-live="polite">{plainText(message.text)}</p>}
      {message.sources.length > 0 && !waiting && <Sources sources={message.sources} />}
    </div>
  );
}

function Sources({ sources }: { sources: Source[] }) {
  return (
    <details className={styles.sources}>
      <summary>From {sources.length === 1 ? "1 note" : `${sources.length} notes`}</summary>
      <ul>
        {sources.map((source) => (
          <li key={`${source.title}-${source.heading}`}>
            {source.url
              ? <a href={source.url} target="_blank" rel="noopener noreferrer">
                  {source.heading}
                  <OpenRecordIcon size={ICON_SIZE.inline} aria-hidden />
                </a>
              : source.heading}
            <span className={styles.muted}>
              {" · "}{source.title}, checked {formatDate(source.checked_on)}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}
