/*
  The director's dashboard (F15).

  Answers three questions: which jobs made money, which lost it, and
  what is unfinished. Quoted margin, operational margin, cash collected
  and cash paid are four tiles with their own captions and are never
  added together. Every tile opens the records it was built from.
*/

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ButtonLink } from "../../components/Button";
import DataTable, { type Column } from "../../components/DataTable";
import { SelectField, TextField } from "../../components/Field";
import FilterTabs from "../../components/FilterTabs";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { businessToday, formatDate, formatMoney } from "../../lib/format";
import { fetchDashboard, summaryPdfUrl, type MetricCard, type MetricRow } from "./api";
import { formatFigure } from "./figures";
import { dashboardQuery, PERIODS, PROJECT_STATUSES, SYSTEM_TYPES } from "./filters";
import styles from "./dashboard.module.css";

const DEFAULT_PERIOD = "month";

const JOB_COLUMNS: readonly Column<MetricRow>[] = [
  { header: "Order", render: (row) => <Reference>{row.reference}</Reference> },
  { header: "Customer", render: (row) => row.label },
  { header: "Completed", render: (row) => (row.date ? formatDate(row.date) : "—") },
  {
    header: "Operational margin", numeric: true,
    render: (row) => <span className={Number(row.amount) < 0 ? styles.loss : undefined}>
      {formatMoney(row.amount ?? 0)}
    </span>,
  },
];

export default function DashboardPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const period = params.get("period") ?? DEFAULT_PERIOD;
  const query = dashboardQuery(params);

  function update(name: string, value: string) {
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (value) next.set(name, value);
      else next.delete(name);
      if (name === "period" && value === "custom" && !next.get("from")) {
        next.set("from", `${businessToday().slice(0, 7)}-01`);
        next.set("to", businessToday());
      }
      return next;
    }, { replace: true });
  }

  const result = useQuery({
    queryKey: ["dashboard", query.toString()],
    queryFn: () => fetchDashboard(query),
    placeholderData: keepPreviousData,
  });

  return <>
    <PageHeader title="Director dashboard"
      subtitle={result.data ? result.data.period.label : "Loading the period…"}
      actions={<ButtonLink to={summaryPdfUrl(query)} reloadDocument>Summary PDF</ButtonLink>} />

    <FilterTabs label="Period" options={PERIODS} value={period}
      onChange={(value) => update("period", value)} />
    <div className={styles.toolbar}>
      {period === "custom" && <>
        <TextField label="From" type="date" value={params.get("from") ?? ""}
          onChange={(value) => update("from", value)} />
        <TextField label="To" type="date" value={params.get("to") ?? ""}
          onChange={(value) => update("to", value)} />
      </>}
      <SelectField label="Project status" value={params.get("status") ?? ""}
        options={PROJECT_STATUSES} onChange={(value) => update("status", value)} />
      <SelectField label="System type" value={params.get("system_type") ?? ""}
        options={SYSTEM_TYPES} onChange={(value) => update("system_type", value)} />
    </div>

    {result.isPending && <LoadingMessage label="Working out the figures…" />}
    {result.isError && <ErrorMessage error={result.error} onRetry={result.refetch} />}

    {result.data && <>
      {result.data.groups.map((group) => <section key={group.title} className={styles.group}>
        <h2>{group.title}</h2>
        <div className={styles.cards}>
          {group.cards.map((card) => <Tile key={card.key} card={card} query={query} />)}
        </div>
      </section>)}

      <section className={styles.group}>
        <h2>Jobs by operational margin</h2>
        {result.data.jobs.length === 0
          ? <p className={styles.muted}>No jobs were completed in this period.</p>
          : <DataTable caption="Jobs ranked by operational margin" columns={JOB_COLUMNS}
              rows={result.data.jobs} rowKey={(row) => row.reference}
              onRowClick={(row) => navigate(row.url)} />}
      </section>
    </>}
  </>;
}

function Tile({ card, query }: { card: MetricCard; query: URLSearchParams }) {
  const suffix = query.toString();

  return <Link className={styles.card} to={`/dashboard/${card.key}${suffix ? `?${suffix}` : ""}`}>
    <span className={styles.value}>{formatFigure(card.value, card.kind)}</span>
    <span>{card.label}</span>
    <span className={styles.caption}>{card.caption}</span>
  </Link>;
}
