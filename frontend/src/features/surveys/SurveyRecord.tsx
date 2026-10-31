/*
  One survey in full (F03).

  Shows the latest revision and every earlier one, because what was
  reported and sent back is part of the record. A submitted revision is
  never edited: a correction is the next revision. The action offered
  depends on where the survey stands, and on whether this person may
  review it.
*/

import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { describeError } from "../../api/client";
import Button, { ButtonLink } from "../../components/Button";
import ActivityTimeline from "../../components/activity_timeline";
import ConfirmDialog from "../../components/ConfirmDialog";
import DataTable, { type Column } from "../../components/DataTable";
import { FileField, SelectField, TextAreaField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import { EmptyMessage, ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import StatusPath from "../../components/StatusPath";
import { REVISION_STATUSES } from "../../components/status";
import { formatDate, formatDateTime, formatQuantity } from "../../lib/format";
import { hasRole, useStaffUser } from "../auth/session";
import { fetchStaff } from "../enquiries/api";
import { addPhoto, assignSurvey, fetchSurvey, reviewRevision, submitRevision } from "./api";
import {
  labelFor,
  ORIENTATION_OPTIONS,
  ROOF_TYPE_OPTIONS,
  SYSTEM_TYPE_OPTIONS,
} from "./labels";
import { latestStatus, waitingOn } from "./surveyState";
import type { ReviewDecision, Survey, SurveyRevision } from "./types";
import styles from "./SurveyRecord.module.css";

const STAGES = [
  { key: "draft", label: "Draft" },
  { key: "submitted", label: "Submitted" },
  { key: "approved", label: "Approved" },
];

const PHOTO_FILE_TYPES = ".jpg,.jpeg,.png";

export default function SurveyRecord() {
  const user = useStaffUser();
  const { surveyId = "" } = useParams();
  const [params, setParams] = useSearchParams();

  const { data: survey, isPending, isError, error, refetch } = useQuery({
    queryKey: ["surveys", surveyId],
    queryFn: () => fetchSurvey(surveyId),
  });

  if (isPending) return <LoadingMessage label="Loading survey…" />;
  if (isError) return <ErrorMessage error={error} onRetry={refetch} />;

  const latest = survey.revisions[0];
  const chosen = Number(params.get("revision"));
  const shown =
    survey.revisions.find((revision) => revision.revision_number === chosen) ?? latest;

  return (
    <>
      <PageHeader
        back={{ to: "/surveys", label: "Surveys" }}
        title={<Reference>{survey.enquiry_reference}</Reference>}
        subtitle={survey.customer_name}
        actions={<PrimaryAction survey={survey} />}
      >
        <div className={styles.summary}>
          <StatusBadge status={latestStatus(survey)} />
          <span className={styles.muted}>{waitingOn(survey)}</span>
        </div>
      </PageHeader>

      {latest && <StatusPath stages={STAGES} current={pathStage(latest)} />}
      {user.can_approve_surveys && <AssignmentForm key={survey.revision} survey={survey} />}
      {survey.is_approved && hasRole(user, "sales") && <p><ButtonLink to={`/quotations/new?enquiry=${survey.enquiry}`}>Generate quotation</ButtonLink></p>}

      {!latest && (
        <EmptyMessage>Nothing recorded yet. Start after the site visit.</EmptyMessage>
      )}

      {latest?.review_notes && latest.status !== "approved" && (
        <p className={styles.notice}>
          {latest.reviewed_by_name || "Reviewer"}: {latest.review_notes}
        </p>
      )}

      {latest?.status === "submitted" && <ReviewPanel revision={latest} survey={survey} />}

      {shown && <RevisionDetails revision={shown} survey={survey} />}
      {shown && <ActivityTimeline endpoint={`revisions/${shown.id}/activity/`} revision={shown.revision} />}

      {survey.revisions.length > 1 && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Revision history</h2>
          <DataTable
            caption="Revision history"
            columns={HISTORY_COLUMNS}
            rows={survey.revisions}
            rowKey={(revision) => revision.id}
            selectedKey={shown?.id}
            onRowClick={(revision) =>
              setParams({ revision: String(revision.revision_number) }, { replace: true })
            }
          />
        </section>
      )}
    </>
  );
}


// ============================================================
// What can be done next
// ============================================================

/* A change after a review is the next revision, never an edit. */
function PrimaryAction({ survey }: { survey: Survey }) {
  const user = useStaffUser();
  if (!user.is_administrator && (!hasRole(user, "technician") || survey.assigned_to !== user.id)) return null;
  const latest = survey.revisions[0];

  // Secondary: an approved survey usually needs nothing more.
  if (latest?.status === "approved") {
    return <ButtonLink to={`/surveys/${survey.id}/new`}>Record new revision</ButtonLink>;
  }

  if (latest?.status === "changes_requested") {
    return <div className={styles.actions}>
      <ButtonLink to={`/surveys/${survey.id}/edit/${latest.id}`}>Correct requested revision</ButtonLink>
      <SubmitAction revision={latest} survey={survey} />
    </div>;
  }

  if (!latest || latest.status === "rejected") {
    return (
      <ButtonLink to={`/surveys/${survey.id}/new`} variant="primary">
        {latest ? "Record new revision" : "Record survey"}
      </ButtonLink>
    );
  }

  if (latest.status === "draft") return <div className={styles.actions}>
    <ButtonLink to={`/surveys/${survey.id}/edit/${latest.id}`}>Edit draft</ButtonLink>
    <SubmitAction revision={latest} survey={survey} />
  </div>;
  return null;
}

function SubmitAction({ revision, survey }: { revision: SurveyRevision; survey: Survey }) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const mutation = useMutation({
    mutationFn: () => submitRevision(revision.id, revision.revision),
    onSuccess: () => {
      setConfirming(false);
      queryClient.invalidateQueries({ queryKey: ["surveys"] });
    },
  });

  return (
    <>
      <Button variant="primary" onClick={() => setConfirming(true)}>
        Submit for review
      </Button>

      {confirming && (
        <ConfirmDialog
          title={`Submit revision ${revision.revision_number} of ${survey.enquiry_reference}?`}
          confirmLabel="Submit for review"
          pending={mutation.isPending}
          error={mutation.isError ? describeError(mutation.error) : null}
          onConfirm={() => mutation.mutate()}
          onCancel={() => setConfirming(false)}
        >
          It goes to an operations manager and cannot be edited after this.
          A reviewer may request a correction and resubmission. Changes after
          approval require a new revision.
        </ConfirmDialog>
      )}
    </>
  );
}

/* What each decision does, said before it happens. */
const DECISIONS: Record<ReviewDecision, { label: string; effect: string }> = {
  approved: {
    label: "Approve",
    effect: "Quotations can then be built from it, and it can no longer change.",
  },
  changes_requested: {
    label: "Request changes",
    effect: "The technician corrects this revision and resubmits. The previous submission is retained in the audit history.",
  },
  rejected: {
    label: "Reject",
    effect: "This revision will not be used for a quotation.",
  },
};

function ReviewPanel({ revision, survey }: { revision: SurveyRevision; survey: Survey }) {
  const user = useStaffUser();
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState("");
  const [decision, setDecision] = useState<ReviewDecision | null>(null);

  const mutation = useMutation({
    mutationFn: (chosen: ReviewDecision) =>
      reviewRevision(revision.id, { decision: chosen, notes, revision: revision.revision }),
    onSuccess: () => {
      setDecision(null);
      queryClient.invalidateQueries({ queryKey: ["surveys"] });
    },
  });

  if (!user.can_approve_surveys) return null;

  const hasNotes = notes.trim().length > 0;

  return (
    <section className={styles.review}>
      <h2 className={styles.sectionTitle}>Review revision {revision.revision_number}</h2>

      <TextAreaField
        label="Notes"
        hint="Required when requesting changes or rejecting."
        value={notes}
        onChange={setNotes}
      />

      <div className={styles.actions}>
        <Button variant="primary" onClick={() => setDecision("approved")}>
          Approve
        </Button>
        <Button disabled={!hasNotes} onClick={() => setDecision("changes_requested")}>
          Request changes
        </Button>
        <Button disabled={!hasNotes} onClick={() => setDecision("rejected")}>
          Reject
        </Button>
      </div>

      {decision && (
        <ConfirmDialog
          title={`${DECISIONS[decision].label} revision ${revision.revision_number} of ${survey.enquiry_reference}?`}
          confirmLabel={DECISIONS[decision].label}
          danger={decision === "rejected"}
          pending={mutation.isPending}
          error={mutation.isError ? describeError(mutation.error) : null}
          onConfirm={() => mutation.mutate(decision)}
          onCancel={() => {
            setDecision(null);
            mutation.reset();
          }}
        >
          {DECISIONS[decision].effect}
          {decision === "approved" && survey.is_approved && (
            <>
              {" "}
              It replaces the revision approved now, and any quotation built on
              that one must be reviewed.
            </>
          )}
        </ConfirmDialog>
      )}
    </section>
  );
}


// ============================================================
// What was recorded
// ============================================================

function RevisionDetails({ revision, survey }: { revision: SurveyRevision; survey: Survey }) {
  const user = useStaffUser();
  const isLatest = revision.id === survey.revisions[0].id;

  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>
        Revision {revision.revision_number}
        {!isLatest && (
          <span className={styles.older}>
            {" "}
            <StatusBadge status={REVISION_STATUSES[revision.status]} />
          </span>
        )}
      </h2>

      <div className={styles.groups}>
        <FactGroup title="Roof">
          <Fact label="Type" value={labelFor(ROOF_TYPE_OPTIONS, revision.roof_type)} />
          <Fact
            label="Size"
            value={`${formatQuantity(revision.roof_length_m, "m")} × ${formatQuantity(revision.roof_width_m, "m")}`}
          />
          <Fact label="Usable area" value={formatQuantity(revision.usable_area_sqm, "m²")} />
          <Fact label="Faces" value={labelFor(ORIENTATION_OPTIONS, revision.orientation)} />
          <Fact label="Tilt" value={`${Number(revision.tilt_degrees)}°`} />
          <Fact label="Shading" value={revision.shading_notes} />
        </FactGroup>

        <FactGroup title="Cable and access">
          <Fact
            label="Cable route"
            value={formatQuantity(revision.cable_distance_m, "m")}
          />
          <Fact label="Route notes" value={revision.cable_route_notes} />
          <Fact label="Site access" value={revision.site_access_notes} />
        </FactGroup>

        <FactGroup title="Grid">
          <Fact label="Connection" value={revision.grid_connection_number} />
          <Fact
            label="Sanctioned load"
            value={
              revision.sanctioned_load_kw
                ? formatQuantity(revision.sanctioned_load_kw, "kW")
                : ""
            }
          />
          <Fact
            label="Suitability"
            value={revision.grid_suitable ? "Suitable" : "Not suitable"}
          />
          <Fact label="Notes" value={revision.grid_notes} />
        </FactGroup>

        <FactGroup title="Recommendation">
          <Fact
            label="System"
            value={labelFor(SYSTEM_TYPE_OPTIONS, revision.recommended_system_type)}
          />
          <Fact
            label="Advisory capacity"
            value={formatQuantity(revision.recommended_capacity_kw, "kW")}
          />
          {revision.critical_load_kw && (
            <Fact
              label="Critical load"
              value={formatQuantity(revision.critical_load_kw, "kW")}
            />
          )}
          {revision.backup_duration_hours && (
            <Fact
              label="Backup duration"
              value={formatQuantity(revision.backup_duration_hours, "hours")}
            />
          )}
        </FactGroup>

        <FactGroup title="Visit">
          <Fact label="Surveyed by" value={revision.surveyed_by_name} />
          <Fact label="On site" value={formatDateTime(revision.surveyed_at)} />
          {revision.submitted_at && (
            <Fact label="Submitted" value={formatDateTime(revision.submitted_at)} />
          )}
          {revision.reviewed_at && (
            <Fact
              label="Reviewed"
              value={`${formatDateTime(revision.reviewed_at)}, ${revision.reviewed_by_name}`}
            />
          )}
        </FactGroup>
      </div>

      <Photos revision={revision} canCapture={user.is_administrator || (hasRole(user, "technician") && survey.assigned_to === user.id)} />
    </section>
  );
}

function FactGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className={styles.group}>
      <h3 className={styles.groupTitle}>{title}</h3>
      <dl className={styles.facts}>{children}</dl>
    </div>
  );
}

/* Blank optional facts are left out, so the page shows what is known. */
function Fact({ label, value }: { label: string; value: string }) {
  if (!value) return null;

  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

function Photos({ revision, canCapture }: { revision: SurveyRevision; canCapture: boolean }) {
  return (
    <div className={styles.photoSection}>
      <h3 className={styles.groupTitle}>Photos</h3>

      {revision.photos.length === 0 && (
        <p className={styles.muted}>No photos on this revision.</p>
      )}

      <ul className={styles.photos}>
        {revision.photos.map((photo) => (
          <li key={photo.id} className={styles.photo}>
            <img src={photo.url} alt={photo.caption || "Survey photo"} loading="lazy" />
            {photo.caption && <p className={styles.muted}>{photo.caption}</p>}
          </li>
        ))}
      </ul>

      {revision.is_editable && canCapture && <AddPhoto key={revision.photos.length} revision={revision} />}
    </div>
  );
}

function AddPhoto({ revision }: { revision: SurveyRevision }) {
  const queryClient = useQueryClient();
  const [photo, setPhoto] = useState<File | null>(null);
  const [caption, setCaption] = useState("");

  const mutation = useMutation({
    mutationFn: () => addPhoto(revision.id, photo!, caption),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["surveys"] }),
  });

  return (
    <form
      className={styles.addPhoto}
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate();
      }}
    >
      <FileField
        label="Add a photo"
        accept={PHOTO_FILE_TYPES}
        hint="JPEG or PNG, up to 10 MB."
        onChange={setPhoto}
      />
      <TextField label="Caption" value={caption} onChange={setCaption} />

      {mutation.isError && (
        <p className={styles.error} role="alert">
          {describeError(mutation.error)}
        </p>
      )}

      <Button type="submit" disabled={!photo || mutation.isPending}>
        {mutation.isPending ? "Adding…" : "Add photo"}
      </Button>
    </form>
  );
}


// ============================================================
// Helpers
// ============================================================

const HISTORY_COLUMNS: readonly Column<SurveyRevision>[] = [
  { header: "Revision", numeric: true, render: (revision) => revision.revision_number },
  {
    header: "Status",
    render: (revision) => <StatusBadge status={REVISION_STATUSES[revision.status]} />,
  },
  { header: "Surveyed", render: (revision) => formatDate(revision.surveyed_at) },
  { header: "Review notes", render: (revision) => revision.review_notes || "–" },
];

/* Where a revision sits on the path, including the ways one can end. */
function pathStage(revision: SurveyRevision) {
  if (revision.status === "superseded") return "approved";

  return revision.status === "changes_requested" || revision.status === "rejected"
    ? "submitted"
    : revision.status;
}


function AssignmentForm({ survey }: { survey: Survey }) {
  const staff = useQuery({ queryKey: ["staff"], queryFn: fetchStaff });
  const [technician, setTechnician] = useState(survey.assigned_to ? String(survey.assigned_to) : "");
  const queryClient = useQueryClient();
  const mutation = useMutation({ mutationFn: () => assignSurvey(survey, Number(technician)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["surveys"] }) });
  return <section className={styles.section}>
    <h2 className={styles.sectionTitle}>Assigned technician</h2>
    {staff.isError && <ErrorMessage error={staff.error} onRetry={staff.refetch} />}
    <SelectField label="Technician" value={technician} onChange={setTechnician} placeholder="Choose a technician"
      options={(staff.data ?? []).filter((person) => person.roles.includes("technician") || person.is_administrator).map((person) => ({ value: String(person.id), label: person.name }))} />
    {mutation.isError && <p role="alert" className={styles.error}>{describeError(mutation.error)}</p>}
    <Button disabled={!technician || mutation.isPending} onClick={() => mutation.mutate()}>Assign survey</Button>
  </section>;
}
