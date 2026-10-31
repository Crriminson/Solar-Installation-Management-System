/*
  Follow-up panel for one enquiry (F02).

  Everything sales does to a lead, in one place: see the history, record
  a call, move the lead on.

  Two rules come from the server and are mirrored here so the form asks
  for the right thing rather than letting the user discover it from an
  error: losing a lead needs a reason, and every other move needs a
  next action.
*/

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { changeStatus, fetchContactLog, recordContact } from "./api";
import type { EnquiryListItem, EnquiryStatus } from "./types";
import { ApiError } from "../../api/client";
import styles from "./FollowUpPanel.module.css";

/* Which statuses may follow the current one. Mirrors the server map. */
const NEXT_STATUSES: Record<EnquiryStatus, EnquiryStatus[]> = {
  new: ["contacting", "lost"],
  contacting: ["qualified", "lost"],
  qualified: ["survey_scheduled", "lost"],
  survey_scheduled: ["lost"],
  lost: [],
};

const STATUS_LABELS: Record<EnquiryStatus, string> = {
  new: "New",
  contacting: "Contacting",
  qualified: "Qualified",
  survey_scheduled: "Survey scheduled",
  lost: "Lost",
};

const CHANNELS = [
  { value: "phone", label: "Phone call" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "email", label: "Email" },
  { value: "site_visit", label: "Site visit" },
  { value: "other", label: "Other" },
];

interface Props {
  enquiry: EnquiryListItem;
  onClose: () => void;
}

export default function FollowUpPanel({ enquiry, onClose }: Props) {
  const queryClient = useQueryClient();

  function refreshEverything() {
    queryClient.invalidateQueries({ queryKey: ["enquiries"] });
    queryClient.invalidateQueries({ queryKey: ["contacts", enquiry.id] });
  }

  return (
    <aside className={styles.panel} aria-label={`Enquiry ${enquiry.reference}`}>
      <header className={styles.header}>
        <div>
          <h2 className={styles.title}>{enquiry.reference}</h2>
          <p className={styles.subtitle}>
            {enquiry.site.customer.full_name} · {enquiry.site.customer.phone}
          </p>
        </div>
        <button className={styles.close} onClick={onClose} aria-label="Close">
          ×
        </button>
      </header>

      <CurrentState enquiry={enquiry} />

      {enquiry.status !== "lost" && (
        <>
          <LogContactForm enquiry={enquiry} onDone={refreshEverything} />
          <ChangeStatusForm enquiry={enquiry} onDone={refreshEverything} />
        </>
      )}

      <ContactHistory enquiryId={enquiry.id} />
    </aside>
  );
}


// ============================================================
// Current state
// ============================================================

function CurrentState({ enquiry }: { enquiry: EnquiryListItem }) {
  return (
    <section className={styles.section}>
      <dl className={styles.facts}>
        <dt>Status</dt>
        <dd>{STATUS_LABELS[enquiry.status]}</dd>

        <dt>Owner</dt>
        <dd>{enquiry.owner_name || <span className={styles.warn}>Nobody yet</span>}</dd>

        <dt>Next action</dt>
        <dd>
          {enquiry.next_action || <span className={styles.warn}>None planned</span>}
          {enquiry.next_action_due && (
            <span className={enquiry.is_overdue ? styles.overdue : styles.muted}>
              {" "}
              due {enquiry.next_action_due}
              {enquiry.is_overdue && " — overdue"}
            </span>
          )}
        </dd>
      </dl>

      {enquiry.status === "lost" && enquiry.lost_reason && (
        <p className={styles.lost}>Lost: {enquiry.lost_reason}</p>
      )}
    </section>
  );
}


// ============================================================
// Record a contact
// ============================================================

function LogContactForm({
  enquiry,
  onDone,
}: {
  enquiry: EnquiryListItem;
  onDone: () => void;
}) {
  const [channel, setChannel] = useState("phone");
  const [summary, setSummary] = useState("");
  const [reached, setReached] = useState(true);

  const mutation = useMutation({
    mutationFn: () =>
      recordContact(enquiry.id, {
        channel,
        // The server also stores when this was typed; these differ
        // when someone logs a call after the fact.
        contacted_at: new Date().toISOString(),
        summary,
        reached_customer: reached,
      }),
    onSuccess: () => {
      setSummary("");
      setReached(true);
      onDone();
    },
  });

  return (
    <section className={styles.section}>
      <h3 className={styles.sectionTitle}>Record a contact</h3>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <div className={styles.row}>
          <select
            className={styles.select}
            value={channel}
            onChange={(event) => setChannel(event.target.value)}
            aria-label="How you contacted them"
          >
            {CHANNELS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          {/* An unanswered call is still history worth keeping. */}
          <label className={styles.checkbox}>
            <input
              type="checkbox"
              checked={reached}
              onChange={(event) => setReached(event.target.checked)}
            />
            Reached them
          </label>
        </div>

        <textarea
          className={styles.textarea}
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
          placeholder="What was said, or why there was no answer"
          aria-label="Summary"
        />

        {mutation.isError && (
          <p className={styles.error}>{describeError(mutation.error)}</p>
        )}

        <button
          className={styles.button}
          disabled={!summary.trim() || mutation.isPending}
        >
          {mutation.isPending ? "Saving…" : "Save contact"}
        </button>
      </form>
    </section>
  );
}


// ============================================================
// Move the lead on
// ============================================================

function ChangeStatusForm({
  enquiry,
  onDone,
}: {
  enquiry: EnquiryListItem;
  onDone: () => void;
}) {
  const options = NEXT_STATUSES[enquiry.status];
  const [target, setTarget] = useState<EnquiryStatus>(options[0]);
  const [nextAction, setNextAction] = useState("");
  const [due, setDue] = useState("");
  const [reason, setReason] = useState("");

  const losing = target === "lost";

  const mutation = useMutation({
    mutationFn: () =>
      changeStatus(enquiry.id, {
        status: target,
        reason: losing ? reason : "",
        next_action: losing ? "" : nextAction,
        next_action_due: losing || !due ? null : due,
      }),
    onSuccess: () => {
      setNextAction("");
      setDue("");
      setReason("");
      onDone();
    },
  });

  if (options.length === 0) return null;

  const canSubmit = losing ? reason.trim().length > 0 : nextAction.trim().length > 0;

  return (
    <section className={styles.section}>
      <h3 className={styles.sectionTitle}>Move this lead on</h3>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <div className={styles.row}>
          <select
            className={styles.select}
            value={target}
            onChange={(event) => setTarget(event.target.value as EnquiryStatus)}
            aria-label="New status"
          >
            {options.map((option) => (
              <option key={option} value={option}>
                {STATUS_LABELS[option]}
              </option>
            ))}
          </select>
        </div>

        {/* Losing a lead without a reason teaches the business nothing. */}
        {losing ? (
          <textarea
            className={styles.textarea}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Why was this lead lost?"
            aria-label="Reason lost"
          />
        ) : (
          <div className={styles.row}>
            <input
              className={styles.input}
              value={nextAction}
              onChange={(event) => setNextAction(event.target.value)}
              placeholder="What happens next"
              aria-label="Next action"
            />
            <input
              className={styles.date}
              type="date"
              value={due}
              onChange={(event) => setDue(event.target.value)}
              aria-label="Next action due"
            />
          </div>
        )}

        {mutation.isError && (
          <p className={styles.error}>{describeError(mutation.error)}</p>
        )}

        <button className={styles.button} disabled={!canSubmit || mutation.isPending}>
          {mutation.isPending ? "Saving…" : `Mark ${STATUS_LABELS[target].toLowerCase()}`}
        </button>
      </form>
    </section>
  );
}


// ============================================================
// History
// ============================================================

function ContactHistory({ enquiryId }: { enquiryId: number }) {
  const { data, isPending } = useQuery({
    queryKey: ["contacts", enquiryId],
    queryFn: () => fetchContactLog(enquiryId),
  });

  return (
    <section className={styles.section}>
      <h3 className={styles.sectionTitle}>Contact history</h3>

      {isPending && <p className={styles.muted}>Loading…</p>}

      {data && data.results.length === 0 && (
        <p className={styles.muted}>Nobody has contacted this customer yet.</p>
      )}

      <ul className={styles.history}>
        {data?.results.map((entry) => (
          <li key={entry.id} className={styles.historyItem}>
            <div className={styles.historyHead}>
              <strong>{channelLabel(entry.channel)}</strong>
              {!entry.reached_customer && (
                <span className={styles.noAnswer}>no answer</span>
              )}
              <span className={styles.muted}>{formatDateTime(entry.contacted_at)}</span>
            </div>
            <p className={styles.historyBody}>{entry.summary}</p>
            {entry.staff_name && (
              <p className={styles.muted}>by {entry.staff_name}</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}


// ============================================================
// Helpers
// ============================================================

function channelLabel(value: string) {
  return CHANNELS.find((option) => option.value === value)?.label ?? value;
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/* Shows the server's explanation rather than a generic failure. */
function describeError(error: unknown) {
  if (error instanceof ApiError && error.details) {
    const details = error.details as Record<string, unknown>;
    if (typeof details.detail === "string") return details.detail;

    const firstField = Object.values(details)[0];
    if (Array.isArray(firstField) && typeof firstField[0] === "string") {
      return firstField[0];
    }
  }
  return "Could not save. Please try again.";
}
