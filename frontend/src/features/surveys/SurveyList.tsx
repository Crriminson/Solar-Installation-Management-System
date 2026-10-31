/*
  Survey list and review queue (F03).

  Awaiting review is the approver's queue. Not approved is everything a
  quotation is still waiting on.
*/

import { useNavigate } from "react-router-dom";
import { useQuery, keepPreviousData } from "@tanstack/react-query";

import DataTable, { type Column } from "../../components/DataTable";
import FilterTabs from "../../components/FilterTabs";
import PageHeader from "../../components/PageHeader";
import Pagination from "../../components/Pagination";
import Reference from "../../components/Reference";
import SearchInput from "../../components/SearchInput";
import {
  EmptyMessage,
  ErrorMessage,
  LoadingMessage,
} from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { useListParams } from "../../components/useListParams";
import { formatDate, formatQuantity } from "../../lib/format";
import { QUEUE_REFRESH_MS } from "../enquiries/queue";
import { fetchSurveys } from "./api";
import { latestStatus } from "./surveyState";
import type { Survey } from "./types";
import styles from "./SurveyList.module.css";

const VIEWS = [
  { key: "all", label: "All" },
  { key: "pending", label: "Awaiting review" },
  { key: "open", label: "Not approved" },
];

const COLUMNS: readonly Column<Survey>[] = [
  {
    header: "Enquiry",
    render: (survey) => <Reference>{survey.enquiry_reference}</Reference>,
  },
  { header: "Customer", render: (survey) => survey.customer_name },
  {
    header: "Status",
    render: (survey) => <StatusBadge status={latestStatus(survey)} />,
  },
  {
    header: "Revision",
    numeric: true,
    render: (survey) => survey.revisions[0]?.revision_number ?? "–",
  },
  {
    header: "Recommended",
    render: (survey) => {
      const latest = survey.revisions[0];
      return latest ? formatQuantity(latest.recommended_capacity_kw, "kW") : "–";
    },
  },
  {
    header: "Surveyed",
    render: (survey) => {
      const latest = survey.revisions[0];
      if (!latest) return <span className={styles.muted}>Not yet</span>;

      return (
        <>
          <span className={styles.nowrap}>{formatDate(latest.surveyed_at)}</span>
          <div className={styles.muted}>{latest.surveyed_by_name}</div>
        </>
      );
    },
  },
];

export default function SurveyList() {
  const navigate = useNavigate();
  const list = useListParams();

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["surveys", list.search, list.view, list.page],
    queryFn: () =>
      fetchSurveys({
        search: list.search,
        pending: list.view === "pending",
        open: list.view === "open",
        page: list.page,
      }),
    placeholderData: keepPreviousData,
    refetchInterval: QUEUE_REFRESH_MS,
  });

  return (
    <>
      <PageHeader title="Surveys" />

      <FilterTabs
        label="Filter surveys"
        options={VIEWS}
        value={list.view}
        onChange={list.setView}
      />

      <div className={styles.toolbar}>
        <SearchInput
          label="Search enquiry reference or customer"
          value={list.search}
          onSearch={list.setSearch}
        />
      </div>

      {isPending && <LoadingMessage label="Loading surveys…" />}
      {isError && <ErrorMessage error={error} onRetry={refetch} />}

      {data && data.results.length === 0 && (
        <EmptyMessage>{emptyText(list.search, list.view)}</EmptyMessage>
      )}

      {data && data.results.length > 0 && (
        <>
          <DataTable
            caption="Surveys"
            columns={COLUMNS}
            rows={data.results}
            rowKey={(survey) => survey.id}
            onRowClick={(survey) => navigate(`/surveys/${survey.id}`)}
          />
          <Pagination page={list.page} count={data.count} onChange={list.setPage} />
        </>
      )}
    </>
  );
}

function emptyText(search: string, view: string) {
  if (search) return `No survey matches "${search}".`;
  if (view === "pending") return "No surveys are waiting for review.";
  if (view === "open") return "Every survey is approved.";
  return "No surveys yet. Open one from a qualified enquiry.";
}
