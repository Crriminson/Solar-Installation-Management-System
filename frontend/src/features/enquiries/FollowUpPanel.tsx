/*
  Follow-up panel for one enquiry (F02).

  Everything sales does to a lead, in one place: see what it is, give it
  an owner, record a call, move it on.

  The server sends the moves open from the current status, so this
  screen offers only legal ones without keeping its own copy of the
  rules. It still asks for what each move needs, so people are not left
  to discover a rule from an error: losing a lead needs a reason, and
  every other move needs a next action with a date.
*/

import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { describeError } from "../../api/client";
import Button from "../../components/Button";
import ActivityTimeline from "../../components/activity_timeline";
import ConfirmDialog from "../../components/ConfirmDialog";
import {
  SelectField,
  TextAreaField,
  TextField,
} from "../../components/Field";
import Reference from "../../components/Reference";
import SidePanel from "../../components/SidePanel";
import StatusBadge from "../../components/StatusBadge";
import StatusPath from "../../components/StatusPath";
import { ENQUIRY_STATUSES } from "../../components/status";
import {
  dateTimeInputToIso,
  formatDate,
  formatDateTime,
  formatMoney,
  formatPhone,
  formatQuantity,
  nowForDateTimeInput,
} from "../../lib/format";
import { startSurvey } from "../surveys/api";
import { hasRole, useStaffUser } from "../auth/session";
import {
  assignEnquiry,
  billDownloadUrl,
  changeStatus,
  fetchContactLog,
  fetchStaff,
  recordContact,
  reviewDuplicate,
} from "./api";
import NextStep from "./NextStep";
import type { EnquiryListItem, EnquiryStatus } from "./types";
import styles from "./FollowUpPanel.module.css";

const STAGES = [
  { key: "new", label: "New" },
  { key: "contacting", label: "Contacting" },
  { key: "qualified", label: "Qualified" },
  { key: "survey_scheduled", label: "Survey scheduled" },
];

/* What sales should have in hand before moving on. Spec.md, F02. */
const STAGE_GUIDANCE: Record<string, string> = {
  new: "Reach the customer and give this lead an owner.",
  contacting:
    "Before qualifying: roof, consumption, grid connection, requirements, documents.",
  qualified: "Book the site survey with the customer.",
  survey_scheduled: "Waiting on the site survey.",
};

/* A survey follows qualification. */
const SURVEY_READY_STATUSES: readonly EnquiryStatus[] = ["qualified", "survey_scheduled"];

const CHANNEL_OPTIONS = [
  { value: "phone", label: "Phone call" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "email", label: "Email" },
  { value: "site_visit", label: "Site visit" },
  { value: "other", label: "Other" },
];

const SYSTEM_TYPE_LABELS: Record<string, string> = {
  on_grid: "On-grid",
  off_grid: "Off-grid",
  undecided: "Not decided",
};

interface Props {
  enquiry: EnquiryListItem;
  onClose: () => void;
}

export default function FollowUpPanel({ enquiry, onClose }: Props) {
  const queryClient = useQueryClient();
  const user = useStaffUser();
  const canWrite = hasRole(user, "sales") || hasRole(user, "operations_manager");

  function refreshEverything() {
    queryClient.invalidateQueries({ queryKey: ["enquiries"] });
    queryClient.invalidateQueries({ queryKey: ["contacts", enquiry.id] });
    queryClient.invalidateQueries({ queryKey: ["activity"] });
  }

  const { customer } = enquiry.site;
  const isOpen = enquiry.status !== "lost";

  return (
    <SidePanel label={`Enquiry ${enquiry.reference}`} onClose={onClose}>
      <header className={styles.header}>
        <h2 className={styles.title}>
          <Reference>{enquiry.reference}</Reference>
        </h2>
        <p className={styles.subtitle}>
          {customer.full_name} · {formatPhone(customer.phone)}
        </p>
        <StatusBadge status={ENQUIRY_STATUSES[enquiry.status]} />
      </header>

      {isOpen && (
        <StatusPath
          stages={STAGES}
          current={enquiry.status}
          guidance={STAGE_GUIDANCE[enquiry.status]}
        />
      )}

      <Details enquiry={enquiry} />
      {canWrite && enquiry.is_possible_duplicate && <DuplicateReview enquiry={enquiry} onDone={refreshEverything} />}
      {enquiry.duplicate_review && <p>Duplicate review: {enquiry.duplicate_review}. {enquiry.duplicate_review_reason}</p>}

      {canWrite && SURVEY_READY_STATUSES.includes(enquiry.status) && (
        <SurveyLink enquiry={enquiry} />
      )}

      {isOpen && canWrite && (
        <>
          <OwnerForm enquiry={enquiry} onDone={refreshEverything} />
          <LogContactForm enquiry={enquiry} onDone={refreshEverything} />
          {/* Background refreshes keep typed input and its original edit revision. */}
          <ChangeStatusForm
            enquiry={enquiry}
            onDone={refreshEverything}
          />
        </>
      )}

      <ContactHistory enquiryId={enquiry.id} />
      <ActivityTimeline endpoint={`enquiries/${enquiry.id}/activity/`} revision={enquiry.revision} />
    </SidePanel>
  );
}


// ============================================================
// What this enquiry is
// ============================================================

function Details({ enquiry }: { enquiry: EnquiryListItem }) {
  const { site } = enquiry;

  return (
    <section className={styles.section}>
      <dl className={styles.facts}>
        <dt>Next step</dt>
        <dd>
          <NextStep enquiry={enquiry} />
        </dd>

        <dt>Site</dt>
        <dd>
          {site.address_line}, {site.city}, {site.state} {site.pincode}
          {site.shadow_free_roof_area_sqm && (
            <div className={styles.muted}>
              {formatQuantity(site.shadow_free_roof_area_sqm, "m²")} shadow-free
            </div>
          )}
        </dd>

        <dt>Wants</dt>
        <dd>
          {SYSTEM_TYPE_LABELS[enquiry.requested_system_type]}
          {enquiry.requested_capacity_kw &&
            `, ${formatQuantity(enquiry.requested_capacity_kw, "kW")}`}
        </dd>

        {/* Bill and units are shown separately. Neither implies the
            other, so we never display one in place of a missing other. */}
        <dt>Bill</dt>
        <dd>
          {enquiry.monthly_bill_amount
            ? `${formatMoney(enquiry.monthly_bill_amount)} a month`
            : "Not given"}
          {enquiry.billing_period_start && enquiry.billing_period_end && (
            <div className={styles.muted}>
              {formatDate(enquiry.billing_period_start)} to{" "}
              {formatDate(enquiry.billing_period_end)}
            </div>
          )}
          {enquiry.has_electricity_bill && (
            <div>
              <a href={billDownloadUrl(enquiry.id)}>Download bill</a>
            </div>
          )}
        </dd>

        <dt>Units</dt>
        <dd>
          {enquiry.monthly_consumption_kwh
            ? `${formatQuantity(enquiry.monthly_consumption_kwh, "kWh")} a month`
            : "Not given"}
        </dd>

        {enquiry.electricity_connection_number && (
          <>
            <dt>Connection</dt>
            <dd>
              <Reference>{enquiry.electricity_connection_number}</Reference>
            </dd>
          </>
        )}

        {enquiry.notes && (
          <>
            <dt>Notes</dt>
            <dd>{enquiry.notes}</dd>
          </>
        )}

        <dt>Received</dt>
        <dd>{formatDateTime(enquiry.created_at)}</dd>
      </dl>

      {enquiry.is_possible_duplicate && (
        <p className={styles.notice}>
          Another customer has this phone number. Check whether they are the
          same person.
        </p>
      )}

      {enquiry.lost_reason && (
        <p className={styles.notice}>Lost: {enquiry.lost_reason}</p>
      )}
    </section>
  );
}


// ============================================================
// The survey
// ============================================================

/* Opening is safe to repeat: an enquiry has one survey. */
function SurveyLink({ enquiry }: { enquiry: EnquiryListItem }) {
  const navigate = useNavigate();

  const mutation = useMutation({
    mutationFn: () => startSurvey(enquiry.id),
    onSuccess: (survey) => navigate(`/surveys/${survey.id}`),
  });

  return (
    <section className={styles.section}>
      <Button disabled={mutation.isPending} onClick={() => mutation.mutate()}>
        {mutation.isPending ? "Opening…" : "Open survey"}
      </Button>

      {mutation.isError && (
        <p className={styles.error} role="alert">
          {describeError(mutation.error)}
        </p>
      )}
    </section>
  );
}


// ============================================================
// Give it an owner
// ============================================================

function OwnerForm({
  enquiry,
  onDone,
}: {
  enquiry: EnquiryListItem;
  onDone: () => void;
}) {
  const staff = useQuery({ queryKey: ["staff"], queryFn: fetchStaff });
  const [revision, setRevision] = useState(enquiry.revision);

  const [owner, setOwner] = useState(enquiry.owner ? String(enquiry.owner) : "");
  const [nextAction, setNextAction] = useState(enquiry.next_action);
  const [due, setDue] = useState(enquiry.next_action_due ?? "");

  const mutation = useMutation({
    mutationFn: () =>
      assignEnquiry(enquiry.id, {
        revision,
        owner: Number(owner),
        next_action: nextAction,
        next_action_due: due || null,
      }),
    onSuccess: (updated) => { setRevision(updated.revision); onDone(); },
  });

  const options = (staff.data ?? []).filter((person) => person.roles.includes("sales") || person.is_administrator).map((person) => ({
    value: String(person.id),
    label: person.name,
  }));

  return (
    <section className={styles.section}>
      <h3 className={styles.sectionTitle}>Owner and next action</h3>

      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <SelectField
          label="Owner"
          value={owner}
          onChange={setOwner}
          options={options}
          placeholder="Choose someone"
        />
        <TextField label="Next action" value={nextAction} onChange={setNextAction} />
        {staff.isError && <p role="alert">{describeError(staff.error)} <Button onClick={() => staff.refetch()}>Retry</Button></p>}
        <TextField label="Due" type="date" value={due} onChange={setDue} />

        {mutation.isError && (
          <p className={styles.error} role="alert">
            {describeError(mutation.error)}
          </p>
        )}

        <Button
          type="submit"
          disabled={!owner || !nextAction.trim() || !due || mutation.isPending}
        >
          {mutation.isPending ? "Saving…" : "Save owner"}
        </Button>
      </form>
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
  const [contactedAt, setContactedAt] = useState(nowForDateTimeInput);

  const mutation = useMutation({
    mutationFn: () =>
      recordContact(enquiry.id, {
        channel,
        // When it happened, which may be earlier than now if the call
        // is being logged after the fact. The server keeps both.
        contacted_at: dateTimeInputToIso(contactedAt),
        summary,
        reached_customer: reached,
      }),
    onSuccess: () => {
      setSummary("");
      setReached(true);
      setContactedAt(nowForDateTimeInput());
      onDone();
    },
  });

  return (
    <section className={styles.section}>
      <h3 className={styles.sectionTitle}>Record a contact</h3>

      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <SelectField
          label="How"
          value={channel}
          onChange={setChannel}
          options={CHANNEL_OPTIONS}
        />
        <TextField
          label="When"
          type="datetime-local"
          value={contactedAt}
          onChange={setContactedAt}
        />

        {/* An unanswered call is still history worth keeping. */}
        <label className={styles.checkbox}>
          <input
            type="checkbox"
            checked={reached}
            onChange={(event) => setReached(event.target.checked)}
          />
          Reached the customer
        </label>

        <TextAreaField
          label="What was said, or why there was no answer"
          value={summary}
          onChange={setSummary}
        />

        {mutation.isError && (
          <p className={styles.error} role="alert">
            {describeError(mutation.error)}
          </p>
        )}

        <Button
          type="submit"
          disabled={!summary.trim() || !contactedAt || mutation.isPending}
        >
          {mutation.isPending ? "Saving…" : "Save contact"}
        </Button>
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
  const options = enquiry.next_statuses;
  const editRevision = useRef<number | null>(null);
  const [selectedTarget, setSelectedTarget] = useState<EnquiryStatus | null>(null);
  const target = selectedTarget ?? options[0];
  const [nextAction, setNextAction] = useState("");
  const [due, setDue] = useState("");
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  function markEditing() {
    if (editRevision.current === null) editRevision.current = enquiry.revision;
  }

  const losing = target === "lost";

  const mutation = useMutation({
    mutationFn: () =>
      changeStatus(enquiry.id, {
        revision: editRevision.current ?? enquiry.revision,
        qualification_checks: checks,
        status: target,
        reason: losing || target === "qualified" ? reason : "",
        next_action: losing ? "" : nextAction,
        next_action_due: losing ? null : due,
      }),
    onSuccess: () => {
      editRevision.current = null;
      setSelectedTarget(null);
      setChecks({}); setNextAction(""); setDue(""); setReason("");
      onDone();
    },
  });

  const canSubmit = losing
    ? reason.trim().length > 0
    : nextAction.trim().length > 0 && Boolean(due);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    // Losing a lead cannot be undone, so it is confirmed first.
    if (losing) setConfirming(true);
    else mutation.mutate();
  }

  const targetLabel = ENQUIRY_STATUSES[target].label;

  return (
    <section className={styles.section}>
      <h3 className={styles.sectionTitle}>Move this lead on</h3>

      <form className={styles.form} onSubmit={handleSubmit}>
        <SelectField
          label="New status"
          value={target}
          onChange={(value) => { markEditing(); setSelectedTarget(value as EnquiryStatus); }}
          options={options.map((option) => ({
            value: option,
            label: ENQUIRY_STATUSES[option].label,
          }))}
        />

        {/* Losing a lead without a reason teaches the business nothing. */}
        {target === "qualified" && <fieldset>
          <legend>Qualification checks</legend>
          {Object.entries({ roof: "Roof availability checked", consumption: "Consumption reviewed", grid: "Grid connection suitability checked", requirements: "Customer requirements confirmed", documents: "Documents checked for completeness" }).map(([name, label]) =>
            <label key={name} className={styles.checkbox}><input type="checkbox" checked={checks[name] ?? false}
              onChange={(event) => { markEditing(); setChecks((current) => ({ ...current, [name]: event.target.checked })); }} />{label}</label>)}
          <TextAreaField label="Why does this lead qualify?" required value={reason} onChange={(value) => { markEditing(); setReason(value); }} />
        </fieldset>}
        {losing ? (
          <TextAreaField
            label="Why was this lead lost?"
            required
            value={reason}
            onChange={(value) => { markEditing(); setReason(value); }}
          />
        ) : (
          <>
            <TextField
              label="What happens next"
              required
              value={nextAction}
              onChange={(value) => { markEditing(); setNextAction(value); }}
            />
            <TextField
              label="Due"
              required
              type="date"
              value={due}
              onChange={(value) => { markEditing(); setDue(value); }}
            />
          </>
        )}

        {mutation.isError && !confirming && (
          <p className={styles.error} role="alert">
            {describeError(mutation.error)}
          </p>
        )}

        <Button
          type="submit"
          variant="primary"
          disabled={!canSubmit || mutation.isPending}
        >
          {mutation.isPending ? "Saving…" : `Mark as ${targetLabel.toLowerCase()}`}
        </Button>
      </form>

      {confirming && (
        <ConfirmDialog
          title={`Mark ${enquiry.reference} as lost?`}
          confirmLabel="Mark as lost"
          danger
          pending={mutation.isPending}
          error={mutation.isError ? describeError(mutation.error) : null}
          onConfirm={() => mutation.mutate()}
          onCancel={() => setConfirming(false)}
        >
          The lead closes and leaves the sales queue. It cannot be reopened.
        </ConfirmDialog>
      )}
    </section>
  );
}


// ============================================================
// History
// ============================================================

function ContactHistory({ enquiryId }: { enquiryId: number }) {
  const { data, isPending, error, isError, refetch } = useQuery({
    queryKey: ["contacts", enquiryId],
    queryFn: () => fetchContactLog(enquiryId),
  });

  return (
    <section className={styles.section}>
      <h3 className={styles.sectionTitle}>Contact history</h3>

      {isPending && <p className={styles.muted}>Loading…</p>}
      {isError && <p role="alert">{describeError(error)} <Button onClick={() => refetch()}>Retry</Button></p>}

      {data && data.results.length === 0 && (
        <p className={styles.muted}>Nobody has contacted this customer yet.</p>
      )}

      <ul className={styles.history}>
        {data?.results.map((entry) => (
          <li key={entry.id} className={styles.historyItem}>
            <div className={styles.historyHead}>
              <strong>{channelLabel(entry.channel)}</strong>
              {!entry.reached_customer && (
                <span className={styles.noAnswer}>No answer</span>
              )}
              <span className={styles.muted}>{formatDateTime(entry.contacted_at)}</span>
            </div>
            <p className={styles.historyBody}>{entry.summary}</p>
            {entry.staff_name && <p className={styles.muted}>By {entry.staff_name}</p>}
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
  return CHANNEL_OPTIONS.find((option) => option.value === value)?.label ?? value;
}


function DuplicateReview({ enquiry, onDone }: { enquiry: EnquiryListItem; onDone: () => void }) {
  const [decision, setDecision] = useState("distinct");
  const [reason, setReason] = useState("");
  const mutation = useMutation({ mutationFn: () => reviewDuplicate(enquiry, decision, reason), onSuccess: onDone });
  return <section className={styles.section}>
    <h3 className={styles.sectionTitle}>Review possible duplicate</h3>
    <p>A phone number or site address matches {enquiry.duplicate_candidate?.full_name}, {formatPhone(enquiry.duplicate_candidate?.phone ?? "")}. Both incoming records are retained.</p>
    <SelectField label="Review outcome" value={decision} onChange={setDecision} options={[
      { value: "distinct", label: "Different customer or separate request" }, { value: "confirmed", label: "Confirmed duplicate — retain for history" },
    ]} />
    <TextAreaField label="Review reason" required value={reason} onChange={setReason} />
    {mutation.isError && <p role="alert" className={styles.error}>{describeError(mutation.error)}</p>}
    <Button disabled={!reason.trim() || mutation.isPending} onClick={() => mutation.mutate()}>Record duplicate review</Button>
  </section>;
}
