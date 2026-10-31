/* Frozen quotation details, separated tax/subsidy values and confirmed document actions. */

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { describeError } from "../../api/client";
import Button, { ButtonLink } from "../../components/Button";
import ActivityTimeline from "../../components/activity_timeline";
import ConfirmDialog from "../../components/ConfirmDialog";
import DataTable, { type Column } from "../../components/DataTable";
import { TextAreaField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { QUOTE_STATUSES } from "../../components/status";
import { formatDate, formatDateTime, formatMoney, formatQuantity } from "../../lib/format";
import { fetchQuotation, quotationAction } from "./api";
import type { Quotation, QuoteLine } from "./types";
import styles from "./quotations.module.css";

const COLUMNS: readonly Column<QuoteLine>[] = [
  { header: "Component", render: (line) => <>{line.description}<div className={styles.muted}>{line.sku}</div></> },
  { header: "Quantity", numeric: true, render: (line) => formatQuantity(line.quantity, line.unit) },
  { header: "Unit price excl. GST", numeric: true, render: (line) => formatMoney(line.unit_price_excl_tax) },
  { header: "Net excl. GST", numeric: true, render: (line) => formatMoney(line.net_excl_tax) },
  { header: "GST", numeric: true, render: (line) => <>{formatMoney(line.tax_amount)} ({line.gst_rate_percent}%)</> },
  { header: "Total incl. GST", numeric: true, render: (line) => formatMoney(line.gross_incl_tax) },
];

export default function QuotationRecord() {
  const { quoteId = "" } = useParams();
  const result = useQuery({ queryKey: ["quotations", quoteId], queryFn: () => fetchQuotation(quoteId) });
  if (result.isPending) return <LoadingMessage label="Loading quotation…" />;
  if (result.isError) return <ErrorMessage error={result.error} onRetry={result.refetch} />;
  return <QuotationDetails key={result.data.id} quotation={result.data} />;
}

function QuotationDetails({ quotation }: { quotation: Quotation }) {
  const { snapshot, terms } = quotation;
  const [action, setAction] = useState<string | null>(null);
  const [actionQuotation, setActionQuotation] = useState<Quotation | null>(null);
  const [reason, setReason] = useState("");
  const key = useRef(crypto.randomUUID());
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => quotationAction(actionQuotation!, action!, key.current, reason),
    onSuccess: () => { setAction(null); queryClient.invalidateQueries({ queryKey: ["quotations"] }); },
  });

  function openAction(next: string) {
    key.current = crypto.randomUUID();
    mutation.reset();
    setActionQuotation(quotation);
    setAction(next);
  }

  return <>
    <PageHeader back={{ to: "/quotations", label: "Quotations" }} title={<Reference>{quotation.reference} · R{quotation.revision_number}</Reference>}
      subtitle={`${snapshot.customer.name} · ${snapshot.customer.phone}`}
      actions={quotation.actions.includes("issue") && <Button variant="primary" onClick={() => openAction("issue")}>Issue quotation</Button>}>
      <StatusBadge status={QUOTE_STATUSES[quotation.display_status]} />
    </PageHeader>
    {quotation.requires_survey_review && <p className={styles.error}>A newer survey revision was approved. Review it and regenerate before issuing or accepting this quotation.</p>}
    <section className={styles.section}>
      <h2>Source and terms</h2>
      <dl className={styles.facts}>
        <dt>Site</dt><dd>{snapshot.site.address}, {snapshot.site.city}, {snapshot.site.state} {snapshot.site.pincode}</dd>
        <dt>Survey</dt><dd>Revision {snapshot.survey.number} · {formatQuantity(snapshot.survey.recommended_capacity_kw, "kW")} · {snapshot.survey.recommended_system_type.replace("_", " ")}</dd>
        <dt>Reviewed package</dt><dd>{snapshot.package.name} · Version {snapshot.package.version}</dd>
        <dt>Created</dt><dd>{formatDateTime(quotation.created_at)}</dd>
        <dt>Issued</dt><dd>{quotation.issued_at ? formatDateTime(quotation.issued_at) : "Draft — not issued"}</dd>
        <dt>Valid until</dt><dd>{quotation.valid_until ? formatDate(quotation.valid_until) : `${quotation.validity_days} days from issue`}</dd>
        <dt>Payment plan</dt><dd>{terms.plan === "advance" ? `${terms.advance_percent}% advance, ${formatMoney(terms.advance_amount_incl_tax)} incl. GST` : "Full payment before dispatch"}</dd>
        <dt>Balance</dt><dd>{formatMoney(terms.balance_amount_incl_tax)} incl. GST, due on delivery completion</dd>
        {terms.notes && <><dt>Agreed terms</dt><dd>{terms.notes}</dd></>}
      </dl>
    </section>
    <section className={styles.section}>
      <h2>Generated components and charges</h2>
      <DataTable caption="Quotation components" columns={COLUMNS} rows={quotation.lines} rowKey={(line) => line.id} />
      <dl className={styles.totals}>
        <dt>Subtotal excl. GST</dt><dd>{formatMoney(quotation.subtotal_excl_tax)}</dd>
        <dt>GST</dt><dd>{formatMoney(quotation.tax_amount)}</dd>
        <dt><strong>Gross payable incl. GST</strong></dt><dd><strong>{formatMoney(quotation.gross_payable_incl_tax)}</strong></dd>
      </dl>
      <p className={styles.muted}>{snapshot.rounding}</p>
    </section>
    {quotation.subsidy.length > 0 && <section className={styles.section}>
      <h2>Estimated subsidy</h2>
      <p>Estimates are not approvals or disbursements. Gross payable is unchanged.</p>
      {quotation.subsidy.map((estimate) => <div className={styles.estimate} key={estimate.rule_id}>
        <h3>{estimate.scheme} · Version {estimate.version}</h3>
        <p>{estimate.rule_type === "generation" ? `${formatMoney(estimate.amount)} per kWh generation incentive` : `${formatMoney(estimate.amount)} estimated capital subsidy`}</p>
        <p>Assumptions: {Object.entries(estimate.assumptions).map(([name, value]) => `${name.replaceAll("_", " ")}: ${String(value)}`).join(" · ")}</p>
        <p className={styles.muted}>{estimate.provenance}</p>
        <a href={estimate.source_url} target="_blank" rel="noreferrer">Source · checked {formatDate(estimate.last_checked)}</a>
      </div>)}
    </section>}
    <div className={styles.actions}>
      {quotation.actions.includes("generate_revision") && <ButtonLink to={`/quotations/new?previous=${quotation.id}`}>{quotation.status === "draft" ? "Regenerate draft" : "Generate revised quotation"}</ButtonLink>}
      {quotation.actions.includes("reject") && <Button onClick={() => openAction("reject")}>Record rejection</Button>}
      <ButtonLink to={`/quotations?enquiry=${quotation.enquiry}`}>All revisions</ButtonLink>
    </div>
    {quotation.content_hash && <p className={styles.hash}>Document hash: {quotation.content_hash}</p>}
    <ActivityTimeline endpoint={`quotations/${quotation.id}/activity/`} revision={quotation.revision} />
    {action && <ConfirmDialog title={action === "issue" ? `Issue ${quotation.reference} revision ${quotation.revision_number}?` : `Record rejection of ${quotation.reference}?`}
      confirmLabel={action === "issue" ? "Issue quotation" : "Record rejection"} pending={mutation.isPending}
      error={mutation.isError ? describeError(mutation.error) : null} onConfirm={() => mutation.mutate()} onCancel={() => setAction(null)}>
      {action === "issue" ? <p>This freezes the document for {formatMoney(quotation.gross_payable_incl_tax)} incl. GST and supersedes any previous issued revision. Fresh acceptance is required.</p>
        : <TextAreaField label="Customer's rejection reason" required value={reason} onChange={setReason} />}
    </ConfirmDialog>}
  </>;
}
