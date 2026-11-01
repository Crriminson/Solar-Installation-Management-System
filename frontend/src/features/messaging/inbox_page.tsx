/*
  What customers have sent us (F16).

  The bot relays and collects; it does not answer questions about a
  record. So everything a customer sends lands here, and a person
  replies — on the ticket, on the phone, or by sending them a document.

  A message from a chat we do not recognise is still shown, because
  somebody has to notice it, but it is marked as unlinked: nothing has
  been disclosed to it.
*/

import { useQuery } from "@tanstack/react-query";

import DataTable, { type Column } from "../../components/DataTable";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import { EmptyMessage, ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { formatDateTime } from "../../lib/format";
import { fetchInbox, type InboxMessage } from "./api";
import styles from "./messaging.module.css";

/* Replies arrive while the page is open, so it refreshes itself. */
const REFRESH_MS = 15_000;

const COLUMNS: readonly Column<InboxMessage>[] = [
  {
    header: "From",
    render: (message) =>
      message.customer_name ? (
        <strong>{message.customer_name}</strong>
      ) : (
        <span className={styles.unlinked}>
          Unlinked chat <Reference>{message.chat_id}</Reference>
        </span>
      ),
  },
  { header: "Message", render: (message) => message.text || "(no text)" },
  { header: "Received", render: (message) => formatDateTime(message.received_at) },
];

export default function InboxPage() {
  const inbox = useQuery({
    queryKey: ["telegram-inbox"],
    queryFn: fetchInbox,
    refetchInterval: REFRESH_MS,
  });

  return (
    <>
      <PageHeader
        title="Customer messages"
        subtitle="Replies from customers on Telegram. Answer on the ticket, or by phone."
      />

      {inbox.isPending && <LoadingMessage label="Loading messages…" />}
      {inbox.isError && <ErrorMessage error={inbox.error} onRetry={inbox.refetch} />}

      {inbox.data && inbox.data.results.length === 0 && (
        <EmptyMessage>
          No customer messages yet. They appear here once a customer has linked
          their chat and written to us.
        </EmptyMessage>
      )}

      {inbox.data && inbox.data.results.length > 0 && (
        <DataTable
          caption="Messages received from customers"
          columns={COLUMNS}
          rows={inbox.data.results}
          rowKey={(message) => message.id}
        />
      )}

      <p className={styles.muted}>
        Nothing is sent from here. The bot never answers a question about a
        record — a person does, from the record itself.
      </p>
    </>
  );
}
