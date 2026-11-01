/*
  One customer, and everything we have done for them (F01).

  Spec.md F01: a customer may have several sites, and a site may have
  several projects. Every other screen shows one slice of that; this
  gathers the slices so nobody has to visit five screens to answer one
  question. No cost or margin: Sales and Support read this.
*/

import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import DataTable, { type Column } from "../../components/DataTable";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import StatusBadge from "../../components/StatusBadge";
import { ErrorMessage, LoadingRecord } from "../../components/StateMessage";
import { ENQUIRY_STATUSES } from "../../components/status";
import { ORDER_STATUSES } from "../orders/status";
import { TICKET_STATUSES } from "../support/status";
import { WARRANTY_STATUSES } from "../warranties/status";
import { formatDate, formatMoney, formatPhone } from "../../lib/format";
import { fetchCustomer } from "./api";
import type {
  CustomerEnquiry, CustomerOrder, CustomerTicket, CustomerUnit,
} from "./types";
import styles from "./customers.module.css";

export default function CustomerRecord() {
  const { customerId = "" } = useParams();
  const navigate = useNavigate();

  const result = useQuery({
    queryKey: ["customer", customerId],
    queryFn: () => fetchCustomer(customerId),
  });

  if (result.isPending) return <LoadingRecord label="Loading customer…" />;
  if (result.isError) {
    return <ErrorMessage error={result.error} onRetry={result.refetch} />;
  }

  const customer = result.data;

  const ENQUIRIES: readonly Column<CustomerEnquiry>[] = [
    { header: "Reference", render: (row) => <Reference>{row.reference}</Reference> },
    { header: "Status", render: (row) => <StatusBadge status={ENQUIRY_STATUSES[row.status]} /> },
    { header: "Owner", render: (row) => row.owner_name || "Unassigned" },
    { header: "Raised", render: (row) => formatDate(row.created_at) },
  ];

  const ORDERS: readonly Column<CustomerOrder>[] = [
    { header: "Reference", render: (row) => <Reference>{row.reference}</Reference> },
    { header: "Status", render: (row) => <StatusBadge status={ORDER_STATUSES[row.status]} /> },
    { header: "Gross", numeric: true, render: (row) => formatMoney(row.gross) },
    { header: "Outstanding", numeric: true, render: (row) => formatMoney(row.outstanding) },
  ];

  const EQUIPMENT: readonly Column<CustomerUnit>[] = [
    { header: "Asset", render: (row) => <Reference>{row.asset_id}</Reference> },
    { header: "Serial", render: (row) => <Reference>{row.serial_number || "—"}</Reference> },
    { header: "Product", render: (row) => row.product },
    {
      header: "Cover",
      render: (row) =>
        row.warranty_status === "none"
          ? <span className={styles.muted}>Not covered</span>
          : <StatusBadge status={WARRANTY_STATUSES[row.warranty_status]} />,
    },
    {
      header: "Until",
      render: (row) => (row.covered_until ? formatDate(row.covered_until) : "—"),
    },
  ];

  const TICKETS: readonly Column<CustomerTicket>[] = [
    { header: "Reference", render: (row) => <Reference>{row.reference}</Reference> },
    { header: "Status", render: (row) => <StatusBadge status={TICKET_STATUSES[row.status]} /> },
    { header: "Fault", render: (row) => row.fault },
    { header: "Raised", render: (row) => formatDate(row.complaint_at) },
  ];

  return (
    <>
      <PageHeader
        back={{ to: "/customers", label: "Customers" }}
        title={customer.full_name}
        subtitle={`${formatPhone(customer.phone)}${customer.email ? ` · ${customer.email}` : ""}`}
      />

      <section className={styles.section}>
        <h2>Details</h2>
        <dl className={styles.facts}>
          <dt>Type</dt>
          <dd>{customer.customer_type === "commercial" ? "Commercial" : "Residential"}</dd>
          <dt>Telegram</dt>
          <dd>
            {customer.telegram.linked
              ? `Linked${customer.telegram.chat_name ? ` (${customer.telegram.chat_name})` : ""}`
              : "Not linked"}
          </dd>
          <dt>Sites</dt>
          <dd>
            {customer.sites.length === 0
              ? "None"
              : customer.sites.map((site) => (
                  <div key={site.id}>
                    {site.address_line}, {site.city}, {site.state} {site.pincode}
                  </div>
                ))}
          </dd>
        </dl>
      </section>

      <Section title="Enquiries" rows={customer.enquiries} columns={ENQUIRIES}
        empty="No enquiries." onOpen={(row) => navigate(`/enquiries?selected=${row.id}`)} />

      <Section title="Orders" rows={customer.orders} columns={ORDERS}
        empty="No orders yet." onOpen={(row) => navigate(`/orders/${row.id}`)} />

      <Section title="Equipment and cover" rows={customer.equipment} columns={EQUIPMENT}
        empty="Nothing delivered yet." />

      <Section title="Service tickets" rows={customer.tickets} columns={TICKETS}
        empty="No tickets raised." onOpen={(row) => navigate(`/tickets/${row.id}`)} />
    </>
  );
}

/* One titled block of rows, or a line saying there are none. */
function Section<Row extends { id: number }>({
  title, rows, columns, empty, onOpen,
}: {
  title: string;
  rows: readonly Row[];
  columns: readonly Column<Row>[];
  empty: string;
  onOpen?: (row: Row) => void;
}) {
  return (
    <section className={styles.section}>
      <h2>{title}</h2>
      {rows.length === 0 ? (
        <p className={styles.muted}>{empty}</p>
      ) : (
        <DataTable caption={title} columns={columns} rows={rows}
          rowKey={(row) => row.id} onRowClick={onOpen} />
      )}
    </section>
  );
}
