/*
  The records behind one dashboard figure (F15).

  A number the director cannot trace is not trusted. The headline is
  computed from these same rows on the server, and the CSV holds them
  too, so screen, tile and export cannot disagree.
*/

import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ButtonLink } from "../../components/Button";
import DataTable, { type Column } from "../../components/DataTable";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import { EmptyMessage, ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { formatDate } from "../../lib/format";
import { fetchMetric, metricCsvUrl, type MetricRow } from "./api";
import { formatFigure } from "./figures";
import { dashboardQuery } from "./filters";
import { CsvIcon } from "../../design/icons";

export default function MetricPage() {
  const { metricKey = "" } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const query = dashboardQuery(params);

  const result = useQuery({
    queryKey: ["dashboard-metric", metricKey, query.toString()],
    queryFn: () => fetchMetric(metricKey, query),
  });

  if (result.isPending) return <LoadingMessage label="Loading the records…" />;
  if (result.isError) return <ErrorMessage error={result.error} onRetry={result.refetch} />;

  const metric = result.data;
  const columns: Column<MetricRow>[] = [
    { header: "Reference", render: (row) => <Reference>{row.reference}</Reference> },
    { header: "Name", render: (row) => row.label },
    { header: "Detail", render: (row) => row.detail || "—" },
    { header: "Date", render: (row) => (row.date ? formatDate(row.date) : "—") },
  ];
  if (metric.kind !== "count") {
    columns.push({
      header: metric.kind === "hours" ? "Hours" : "Amount", numeric: true,
      render: (row) => formatFigure(row.amount ?? "0", metric.kind),
    });
  }

  const suffix = query.toString();

  return <>
    <PageHeader back={{ to: `/dashboard${suffix ? `?${suffix}` : ""}`, label: "Dashboard" }}
      title={metric.label} subtitle={`${metric.caption} · ${metric.period}`}
      actions={<ButtonLink to={metricCsvUrl(metricKey, query)} reloadDocument icon={<CsvIcon aria-hidden />}>Export CSV</ButtonLink>} />

    {metric.rows.length === 0
      ? <EmptyMessage>Nothing behind this figure in this period.</EmptyMessage>
      : <DataTable caption={metric.label} columns={columns} rows={metric.rows}
          rowKey={(row) => `${row.url}-${row.reference}-${row.date}-${row.amount}`}
          onRowClick={(row) => navigate(row.url)} />}
  </>;
}
