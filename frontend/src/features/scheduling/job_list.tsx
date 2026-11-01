/*
  The diary (F10).

  Two audiences on one screen. The office sees everyone's work and can
  book more; a technician sees only their own jobs, and the server
  decides that, not this file. The thinner payload a technician receives
  is why some columns are rendered defensively.
*/

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ButtonLink } from "../../components/Button";
import DataTable, { type Column } from "../../components/DataTable";
import FilterTabs from "../../components/FilterTabs";
import PageHeader from "../../components/PageHeader";
import Pagination from "../../components/Pagination";
import SearchInput from "../../components/SearchInput";
import { EmptyMessage, ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { useListParams } from "../../components/useListParams";
import { formatDateTime, formatTime } from "../../lib/format";
import { hasRole, useStaffUser } from "../auth/session";
import { fetchJobs } from "./api";
import { JOB_KINDS, JOB_STATUSES } from "./status";
import type { Job } from "./types";
import styles from "./scheduling.module.css";
import { AddIcon } from "../../design/icons";

const COLUMNS: readonly Column<Job>[] = [
  {
    header: "When",
    render: (job) => job.starts_at && job.ends_at
      ? <>{formatDateTime(job.starts_at)}
          <div className={styles.muted}>to {formatTime(job.ends_at)}</div></>
      : <span className={styles.muted}>Not booked yet</span>,
  },
  { header: "Work", render: (job) => JOB_KINDS[job.kind] ?? job.kind },
  {
    header: "Where",
    render: (job) => <>{job.customer_name}
      <div className={styles.muted}>{job.site_address}</div></>,
  },
  {
    header: "Crew",
    render: (job) => job.assignments
      .map((person) => person.technician_name || person.username)
      .join(", ") || "—",
  },
  { header: "Status", render: (job) => <StatusBadge status={JOB_STATUSES[job.status]} /> },
  {
    header: "Held up by",
    render: (job) => job.is_blocked
      ? <span className={styles.blockedText}>{job.blocked_reason}</span>
      : "—",
  },
];

const VIEWS = [
  { key: "all", label: "All" },
  // Confirmed orders' installations land here until somebody books them.
  { key: "awaiting_scheduling", label: "Awaiting scheduling" },
  { key: "scheduled", label: "Scheduled" },
  { key: "in_progress", label: "In progress" },
  { key: "awaiting_acceptance", label: "Awaiting customer" },
  { key: "completed", label: "Completed" },
];

export default function JobList() {
  const user = useStaffUser();
  const list = useListParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const canBook = hasRole(user, "operations_manager");

  const query = new URLSearchParams(params);
  query.delete("view");
  if (list.view !== "all") query.set("status", list.view);

  const result = useQuery({
    queryKey: ["jobs", query.toString()],
    queryFn: () => fetchJobs(query),
    placeholderData: keepPreviousData,
  });

  return <>
    <PageHeader title="Schedule"
      subtitle={canBook
        ? "Surveys, installations and service visits."
        : "Your assigned visits."}
      actions={canBook &&
        <ButtonLink to="/schedule/new" variant="primary" icon={<AddIcon aria-hidden />}>Book a visit</ButtonLink>} />
    <FilterTabs label="Job status" options={VIEWS} value={list.view}
      onChange={list.setView} />
    <div className={styles.toolbar}>
      <SearchInput label="Search" value={list.search} onSearch={list.setSearch} />
    </div>

    {result.isPending && <LoadingMessage label="Loading the diary…" />}
    {result.isError && <ErrorMessage error={result.error} onRetry={result.refetch} />}
    {result.data?.count === 0 && <EmptyMessage>Nothing booked.</EmptyMessage>}
    {result.data && result.data.count > 0 && <>
      <DataTable caption="Jobs" columns={COLUMNS} rows={result.data.results}
        rowKey={(job) => job.id} onRowClick={(job) => navigate(`/schedule/${job.id}`)} />
      <Pagination page={list.page} count={result.data.count} onChange={list.setPage} />
    </>}
  </>;
}
