/*
  Every customer (F01).

  Until now a customer could only be reached sideways - through an
  enquiry, an order or a serial. This is the way in by name or phone,
  which is how a person asks for someone.

  The counts tell you which rows are worth opening without loading each
  customer's history to find out.
*/

import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import DataTable, { type Column } from "../../components/DataTable";
import PageHeader from "../../components/PageHeader";
import Pagination from "../../components/Pagination";
import Reference from "../../components/Reference";
import SearchInput from "../../components/SearchInput";
import { EmptyMessage, ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { useListParams } from "../../components/useListParams";
import { formatPhone } from "../../lib/format";
import { fetchCustomers } from "./api";
import type { CustomerRow } from "./types";
import styles from "./customers.module.css";

const COLUMNS: readonly Column<CustomerRow>[] = [
  { header: "Name", render: (row) => <strong>{row.full_name}</strong> },
  { header: "Phone", render: (row) => <Reference>{formatPhone(row.phone)}</Reference> },
  { header: "City", render: (row) => row.city || "—" },
  {
    header: "Type",
    render: (row) => (row.customer_type === "commercial" ? "Commercial" : "Residential"),
  },
  { header: "Sites", numeric: true, render: (row) => row.site_count },
  { header: "Enquiries", numeric: true, render: (row) => row.enquiry_count },
  { header: "Orders", numeric: true, render: (row) => row.order_count },
];

export default function CustomerList() {
  const navigate = useNavigate();
  const list = useListParams();

  const customers = useQuery({
    queryKey: ["customers", list.search, list.page],
    queryFn: () => fetchCustomers(list.search, list.page),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title="Customers"
        subtitle="Everyone we have taken an enquiry from."
      />

      <div className={styles.toolbar}>
        <SearchInput
          label="Search name or phone"
          value={list.search}
          onSearch={list.setSearch}
        />
      </div>

      {customers.isPending && <LoadingMessage label="Loading customers…" />}
      {customers.isError && (
        <ErrorMessage error={customers.error} onRetry={customers.refetch} />
      )}

      {customers.data && customers.data.results.length === 0 && (
        <EmptyMessage>
          {list.search
            ? "No customer matches that name or phone."
            : "No customers yet. They are created by the first enquiry."}
        </EmptyMessage>
      )}

      {customers.data && customers.data.results.length > 0 && (
        <>
          <DataTable
            caption="Customers"
            columns={COLUMNS}
            rows={customers.data.results}
            rowKey={(row) => row.id}
            onRowClick={(row) => navigate(`/customers/${row.id}`)}
          />
          <Pagination
            page={list.page}
            count={customers.data.count}
            onChange={list.setPage}
          />
        </>
      )}
    </>
  );
}
