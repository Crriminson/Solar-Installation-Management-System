/*
  The screen the customer is handed the tablet to sign (F06).

  This is deliberately not the staff quotation screen with a button
  added. It reads from the restricted presentation endpoint, so what is
  on the glass is the customer's document and nothing else: no margins,
  no other customers, no navigation into the rest of the app.

  The signature and the typed name go up together with the revision the
  screen was showing, so a quotation that changed underneath is refused
  rather than signed by accident.
*/

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { describeError } from "../../api/client";
import Button from "../../components/Button";
import DataTable, { type Column } from "../../components/DataTable";
import { TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import SignaturePad from "../../components/signature_pad";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { formatDate, formatMoney, formatQuantity } from "../../lib/format";
import { acceptQuotation, fetchPresentation, fetchQuotation } from "./api";
import type { Presentation, QuoteLine } from "./types";
import styles from "./quotations.module.css";

const COLUMNS: readonly Column<QuoteLine>[] = [
  { header: "Item", render: (line) => line.description },
  { header: "Quantity", numeric: true, render: (line) => formatQuantity(line.quantity, line.unit) },
  { header: "Total incl. GST", numeric: true, render: (line) => formatMoney(line.gross_incl_tax) },
];

export default function QuotationAccept() {
  const { quoteId = "" } = useParams();
  const result = useQuery({
    queryKey: ["quotation-present", quoteId],
    queryFn: () => fetchPresentation(quoteId),
  });

  if (result.isPending) return <LoadingMessage label="Loading quotation…" />;
  if (result.isError) return <ErrorMessage error={result.error} onRetry={result.refetch} />;
  return <SigningView quoteId={quoteId} document={result.data} />;
}

function SigningView({ quoteId, document }: { quoteId: string; document: Presentation }) {
  const [customerName, setCustomerName] = useState("");
  const [signature, setSignature] = useState<Blob | null>(null);
  const key = useRef(crypto.randomUUID());
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async () => {
      /* Read the revision now, so we sign the version on screen. */
      const current = await fetchQuotation(quoteId);
      return acceptQuotation(quoteId, current.revision, key.current,
                             customerName, signature!);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quotations"] });
      navigate(`/quotations/${quoteId}`);
    },
  });

  const ready = customerName.trim().length > 0 && signature !== null;

  if (document.accepted) {
    return <>
      <PageHeader title={<Reference>{document.reference}</Reference>}
        subtitle="This quotation has already been accepted." />
      <Button onClick={() => navigate(`/quotations/${quoteId}`)}>Back to the quotation</Button>
    </>;
  }

  return <>
    <PageHeader title={<Reference>{document.reference} · R{document.revision_number}</Reference>}
      subtitle={`${document.snapshot.customer.name} · ${document.snapshot.site.address}, ${document.snapshot.site.city}`} />

    <section className={styles.section}>
      <h2>Your system</h2>
      <DataTable caption="What is included" columns={COLUMNS} rows={document.lines}
        rowKey={(line) => line.id} />
      <dl className={styles.totals}>
        <dt>Subtotal excl. GST</dt><dd>{formatMoney(document.subtotal_excl_tax)}</dd>
        <dt>GST</dt><dd>{formatMoney(document.tax_amount)}</dd>
        <dt><strong>Total payable</strong></dt>
        <dd><strong>{formatMoney(document.gross_payable_incl_tax)}</strong></dd>
      </dl>
    </section>

    <section className={styles.section}>
      <h2>Payment</h2>
      <dl className={styles.facts}>
        <dt>Now</dt>
        <dd>{document.terms.plan === "advance"
          ? `${formatMoney(document.terms.advance_amount_incl_tax)} advance (${document.terms.advance_percent}%)`
          : "Full payment before dispatch"}</dd>
        <dt>On delivery</dt><dd>{formatMoney(document.terms.balance_amount_incl_tax)}</dd>
        {document.valid_until && <><dt>Offer valid until</dt>
          <dd>{formatDate(document.valid_until)}</dd></>}
      </dl>
      {document.subsidy.length > 0 && <p className={styles.muted}>
        You may be eligible for a government subsidy of up to{" "}
        {formatMoney(document.subsidy[0].amount)}. This is an estimate, not an
        approval, and it is not deducted from the amount above.
      </p>}
    </section>

    <section className={styles.section}>
      <h2>Accept this quotation</h2>
      <div className={styles.form}>
        <TextField label="Your full name" required value={customerName}
          onChange={setCustomerName} />
        <SignaturePad label="Your signature" onChange={setSignature} />
        {mutation.isError && <p className={styles.error}>{describeError(mutation.error)}</p>}
        <Button variant="primary" disabled={!ready || mutation.isPending}
          onClick={() => mutation.mutate()}>
          {mutation.isPending ? "Recording…" : `Accept and sign for ${formatMoney(document.gross_payable_incl_tax)}`}
        </Button>
      </div>
    </section>
  </>;
}
