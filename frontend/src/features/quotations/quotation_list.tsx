/* F05 quotation register: URL filters, server sorting and generated document entry. */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ButtonLink } from "../../components/Button";
import DataTable, { type Column } from "../../components/DataTable";
import { SelectField } from "../../components/Field";
import FilterTabs from "../../components/FilterTabs";
import PageHeader from "../../components/PageHeader";
import Pagination from "../../components/Pagination";
import Reference from "../../components/Reference";
import SearchInput from "../../components/SearchInput";
import { EmptyMessage, ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { QUOTE_STATUSES } from "../../components/status";
import { useListParams } from "../../components/useListParams";
import { formatDate, formatMoney } from "../../lib/format";
import { hasRole, useStaffUser } from "../auth/session";
import { fetchQuotations } from "./api";
import type { Quotation } from "./types";
import styles from "./quotations.module.css";

const COLUMNS: readonly Column<Quotation>[] = [
  { header: "Quotation", render: (quote) => <Reference>{quote.reference} · R{quote.revision_number}</Reference> },
  { header: "Customer", render: (quote) => quote.snapshot.customer.name },
  { header: "Status", render: (quote) => <StatusBadge status={QUOTE_STATUSES[quote.display_status]} /> },
  { header: "Gross payable incl. GST", numeric: true, render: (quote) => formatMoney(quote.gross_payable_incl_tax) },
  { header: "Created", render: (quote) => formatDate(quote.created_at) },
  { header: "Valid until", render: (quote) => quote.valid_until ? formatDate(quote.valid_until) : "Not issued" },
];
const VIEWS = [{ key: "all", label: "All" }, { key: "draft", label: "Draft" },
  { key: "issued", label: "Issued" }, { key: "expired", label: "Expired" }, { key: "superseded", label: "Superseded" }];

export default function QuotationList() {
  const user = useStaffUser();
  const list = useListParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const query = new URLSearchParams(params);
  query.delete("view");
  if (list.view !== "all") query.set("status", list.view);
  const result = useQuery({ queryKey: ["quotations", query.toString()], queryFn: () => fetchQuotations(query), placeholderData: keepPreviousData });

  return <>
    <PageHeader title="Quotations" subtitle="Generated from approved surveys and reviewed packages."
      actions={hasRole(user, "sales") && <ButtonLink to="/quotations/new" variant="primary">Generate quotation</ButtonLink>} />
    <FilterTabs label="Quotation status" options={VIEWS} value={list.view} onChange={list.setView} />
    <div className={styles.toolbar}>
      <SearchInput label="Search quotation or customer" value={list.search} onSearch={list.setSearch} />
      <SelectField label="Sort" value={params.get("sort") ?? "-created"} options={[
        { value: "-created", label: "Newest first" }, { value: "created", label: "Oldest first" },
        { value: "-amount", label: "Largest amount" }, { value: "amount", label: "Smallest amount" },
      ]} onChange={(sort) => setParams((current) => { const next = new URLSearchParams(current); next.set("sort", sort); next.delete("page"); return next; })} />
    </div>
    {result.isPending && <LoadingMessage label="Loading quotations…" />}
    {result.isError && <ErrorMessage error={result.error} onRetry={result.refetch} />}
    {result.data?.count === 0 && <EmptyMessage>No quotations match. Generate one from an approved survey.</EmptyMessage>}
    {result.data && result.data.count > 0 && <>
      <DataTable caption="Quotations" columns={COLUMNS} rows={result.data.results} rowKey={(quote) => quote.id}
        onRowClick={(quote) => navigate(`/quotations/${quote.id}`)} />
      <Pagination page={list.page} count={result.data.count} onChange={list.setPage} />
    </>}
  </>;
}
