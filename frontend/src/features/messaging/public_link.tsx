/*
  The page a customer opens from Telegram (F06, F16).

  No sign-in, no navigation, nothing but this one document. The token
  in the URL is the whole authorisation, and the server decides what it
  is worth: a spent or expired link still shows its document, read
  only, and offers nothing.
*/

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import BrandMark from "../../components/BrandMark";
import Button from "../../components/Button";
import { TextField } from "../../components/Field";
import Reference from "../../components/Reference";
import SignaturePad from "../../components/signature_pad";
import { BlockedIcon, DoneIcon, ICON_SIZE } from "../../design/icons";
import { formatDate, formatMoney, formatQuantity } from "../../lib/format";
import type { Presentation } from "../quotations/types";
import { fetchPublicLink, submitPublicLink, type LinkState } from "./api";
import styles from "./public_link.module.css";

/* Why a link is no longer usable, in the customer's words. */
const DEAD_LINK: Record<Exclude<LinkState, "open">, string> = {
  spent: "This link has already been used. The document below is a copy for your records.",
  expired: "This link has expired. Ask us for a new one if you still need to respond.",
  revoked: "This link is no longer active. Please contact us.",
  superseded: "A newer version of this document was sent. Please use the most recent message.",
};

export default function PublicLinkPage() {
  const { token = "" } = useParams();
  const [name, setName] = useState("");
  const [signature, setSignature] = useState<Blob | null>(null);
  const [done, setDone] = useState<"accepted" | "declined" | "confirmed" | null>(null);

  const link = useQuery({
    queryKey: ["public-link", token],
    queryFn: () => fetchPublicLink(token),
    retry: false,
  });

  const submit = useMutation({
    mutationFn: (decision: "accepted" | "declined" | "confirmed") => {
      const fields: Record<string, string> = { customer_name: name.trim(), decision };
      return submitPublicLink(token, fields, signature ?? undefined)
        .then(() => decision);
    },
    onSuccess: (decision) => setDone(decision),
  });

  if (link.isPending) {
    return <Shell><p className={styles.muted}>Loading your document…</p></Shell>;
  }

  if (link.isError) {
    return (
      <Shell>
        <Notice tone="bad">
          This link is not valid. It may have been mistyped, or replaced by a
          newer message.
        </Notice>
      </Shell>
    );
  }

  const data = link.data;

  if (done) {
    return (
      <Shell>
        <Notice tone="good">
          {done === "confirmed"
            ? "Thank you — we have recorded that this is resolved."
            : done === "accepted"
              ? "Thank you — your acceptance has been recorded. We will be in touch about what happens next."
              : "Thank you — we have recorded that you do not wish to go ahead."}
        </Notice>
      </Shell>
    );
  }

  const isOpen = data.state === "open";

  return (
    <Shell>
      {!isOpen && <Notice tone="bad">{DEAD_LINK[data.state]}</Notice>}

      {data.purpose === "sign_quotation" && data.document && (
        <Quotation document={data.document} />
      )}

      {data.purpose === "confirm_ticket" && data.ticket && (
        <section className={styles.card}>
          <h1 className={styles.title}>Service request</h1>
          <Reference>{data.ticket.reference}</Reference>
          <p className={styles.fault}>{data.ticket.fault}</p>
          <p className={styles.muted}>
            Our technician has recorded the work as finished.
          </p>
        </section>
      )}

      {isOpen && (
        <section className={styles.card}>
          {data.purpose === "sign_quotation" ? (
            <>
              <h2 className={styles.heading}>Your decision</h2>
              <TextField
                label="Your full name"
                required
                value={name}
                onChange={setName}
              />
              <SignaturePad label="Sign here" onChange={setSignature} />
              <p className={styles.honest}>
                Drawn signature — in-app evidence of acceptance. Not an Aadhaar
                eSign or a certified digital signature.
              </p>
              <div className={styles.actions}>
                <Button
                  variant="primary"
                  disabled={!name.trim() || !signature || submit.isPending}
                  loading={submit.isPending}
                  onClick={() => submit.mutate("accepted")}
                >
                  Accept this quotation
                </Button>
                <Button
                  disabled={!name.trim() || submit.isPending}
                  onClick={() => submit.mutate("declined")}
                >
                  No thanks
                </Button>
              </div>
            </>
          ) : (
            <>
              <h2 className={styles.heading}>Is this resolved?</h2>
              <TextField
                label="Your full name"
                required
                value={name}
                onChange={setName}
              />
              <div className={styles.actions}>
                <Button
                  variant="primary"
                  disabled={!name.trim() || submit.isPending}
                  loading={submit.isPending}
                  onClick={() => submit.mutate("confirmed")}
                >
                  Yes, it is resolved
                </Button>
              </div>
              <p className={styles.muted}>
                If it is not resolved, reply to our message on Telegram and we
                will come back to you.
              </p>
            </>
          )}

          {submit.isError && (
            <Notice tone="bad">{(submit.error as Error).message}</Notice>
          )}
        </section>
      )}
    </Shell>
  );
}


// ============================================================
// Pieces
// ============================================================

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.page}>
      <header className={styles.bar}>
        <BrandMark />
      </header>
      <main className={styles.content}>{children}</main>
    </div>
  );
}

function Notice({ tone, children }: { tone: "good" | "bad"; children: React.ReactNode }) {
  const Icon = tone === "good" ? DoneIcon : BlockedIcon;
  return (
    <p className={tone === "good" ? styles.good : styles.bad} role="status">
      <Icon size={ICON_SIZE.control} aria-hidden />
      {children}
    </p>
  );
}

function Quotation({ document }: { document: Presentation }) {
  return (
    <>
      <section className={styles.card}>
        <h1 className={styles.title}>Your quotation</h1>
        <Reference>
          {document.reference} · revision {document.revision_number}
        </Reference>
        <dl className={styles.facts}>
          <dt>Prepared for</dt>
          <dd>{document.snapshot.customer.name}</dd>
          <dt>Site</dt>
          <dd>
            {document.snapshot.site.address}, {document.snapshot.site.city}
          </dd>
          <dt>Valid until</dt>
          <dd>{document.valid_until ? formatDate(document.valid_until) : "—"}</dd>
        </dl>
      </section>

      <section className={styles.card}>
        <h2 className={styles.heading}>What is included</h2>
        <ul className={styles.lines}>
          {document.lines.map((line) => (
            <li key={line.sku} className={styles.line}>
              <span>{line.description}</span>
              <span className={styles.quantity}>
                {formatQuantity(line.quantity, line.unit)}
              </span>
              <span className={styles.amount}>
                {formatMoney(line.gross_incl_tax)}
              </span>
            </li>
          ))}
        </ul>

        <dl className={styles.totals}>
          <dt>Subtotal</dt>
          <dd>{formatMoney(document.subtotal_excl_tax)} <span className={styles.basis}>excl. GST</span></dd>
          <dt>GST</dt>
          <dd>{formatMoney(document.tax_amount)}</dd>
          <dt className={styles.grand}>Total payable</dt>
          <dd className={styles.grand}>
            {formatMoney(document.gross_payable_incl_tax)}{" "}
            <span className={styles.basis}>incl. GST</span>
          </dd>
        </dl>
      </section>

      {document.subsidy?.length > 0 && (
        <section className={styles.card}>
          <h2 className={styles.heading}>Estimated subsidy</h2>
          {/* Capital and per-kWh are separate figures and are never
              added together (spec.md F17). */}
          {document.subsidy.map((entry, index) => (
            <p key={index} className={styles.subsidy}>
              {entry.scheme}:{" "}
              {entry.rule_type === "generation"
                ? `${formatMoney(entry.amount)} ${entry.unit}`
                : formatMoney(entry.amount)}
            </p>
          ))}
          <p className={styles.honest}>
            Estimate only — not an approval and not a disbursement. It does not
            reduce the total payable above.
          </p>
        </section>
      )}
    </>
  );
}
