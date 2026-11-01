/*
  The staff side of F16: link a chat, send a document, ask for a
  confirmation.

  Each one reports what happened rather than going quiet, because what
  these do happens somewhere the person cannot see.
*/

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { describeError } from "../../api/client";
import Button from "../../components/Button";
import { TextAreaField } from "../../components/Field";
import Reference from "../../components/Reference";
import { useToast } from "../../components/ToastContext";
import { ICON_SIZE, SignatureIcon, SendIcon } from "../../design/icons";
import { formatDateTime } from "../../lib/format";
import {
  fetchBindings, issueLinkToken, requestConfirmation, revokeBinding, sendQuotation,
} from "./api";
import styles from "./messaging.module.css";

/*
  Linking a customer's chat.

  The code is shown once, here, and is not retrievable afterwards. It
  is single-use and expires, so a code read over a shoulder is worth
  little for long.
*/
export function TelegramLink({ customerId }: { customerId: number }) {
  const confirm = useToast();
  const queryClient = useQueryClient();
  const [issued, setIssued] = useState<{ deep_link: string; token: string } | null>(null);
  const [revoking, setRevoking] = useState<number | null>(null);
  const [reason, setReason] = useState("");

  const bindings = useQuery({
    queryKey: ["bindings", customerId],
    queryFn: () => fetchBindings(customerId),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["bindings", customerId] });

  const issue = useMutation({
    mutationFn: () => issueLinkToken(customerId),
    onSuccess: (data) => {
      setIssued(data);
      confirm("Linking code issued");
    },
  });

  const revoke = useMutation({
    mutationFn: (id: number) => revokeBinding(id, reason),
    onSuccess: () => {
      setRevoking(null);
      setReason("");
      confirm("Chat unlinked");
      refresh();
    },
  });

  const live = (bindings.data?.results ?? []).filter((binding) => binding.is_live);

  return (
    <section className={styles.section}>
      <h3 className={styles.heading}>Telegram</h3>

      {live.length === 0 && (
        <p className={styles.muted}>
          This customer has no linked chat. They will be contacted by phone
          until one is linked.
        </p>
      )}

      {live.map((binding) => (
        <div key={binding.id} className={styles.binding}>
          <div>
            <strong>{binding.chat_name || "Linked chat"}</strong>
            <div className={styles.muted}>
              Linked {formatDateTime(binding.linked_at)}
            </div>
          </div>
          <Button onClick={() => setRevoking(binding.id)}>Unlink</Button>
        </div>
      ))}

      {revoking !== null && (
        <div className={styles.revoke}>
          <TextAreaField
            label="Why is this chat being unlinked?"
            required
            value={reason}
            onChange={setReason}
          />
          <div className={styles.actions}>
            <Button
              variant="danger"
              disabled={!reason.trim() || revoke.isPending}
              loading={revoke.isPending}
              onClick={() => revoke.mutate(revoking)}
            >
              Unlink this chat
            </Button>
            <Button onClick={() => setRevoking(null)}>Cancel</Button>
          </div>
          {revoke.isError && <p className={styles.error}>{describeError(revoke.error)}</p>}
        </div>
      )}

      {issued ? (
        <div className={styles.code}>
          <p className={styles.muted}>
            Send this to the customer now. It is shown only here, works once,
            and expires.
          </p>
          <Reference>{issued.deep_link || issued.token}</Reference>
        </div>
      ) : (
        <Button
          onClick={() => issue.mutate()}
          loading={issue.isPending}
          icon={<SignatureIcon aria-hidden />}
        >
          Issue a linking code
        </Button>
      )}

      {issue.isError && <p className={styles.error}>{describeError(issue.error)}</p>}
    </section>
  );
}


/* Sends the issued quotation PDF and a single-use signing link. */
export function SendQuotationButton({ quotationId }: { quotationId: number }) {
  const confirm = useToast();
  const send = useMutation({
    mutationFn: () => sendQuotation(quotationId),
    onSuccess: () => confirm("Quotation sent to the customer on Telegram"),
  });

  return (
    <>
      <Button
        onClick={() => send.mutate()}
        loading={send.isPending}
        icon={<SendIcon size={ICON_SIZE.control} aria-hidden />}
      >
        Send on Telegram
      </Button>
      {send.isError && <p className={styles.error}>{describeError(send.error)}</p>}
    </>
  );
}


/* Asks the customer to confirm a repair is resolved (F13). */
export function RequestConfirmationButton({ ticketId }: { ticketId: number }) {
  const confirm = useToast();
  const ask = useMutation({
    mutationFn: () => requestConfirmation(ticketId),
    onSuccess: () => confirm("Confirmation request sent on Telegram"),
  });

  return (
    <>
      <Button
        onClick={() => ask.mutate()}
        loading={ask.isPending}
        icon={<SendIcon size={ICON_SIZE.control} aria-hidden />}
      >
        Ask the customer to confirm
      </Button>
      {ask.isError && <p className={styles.error}>{describeError(ask.error)}</p>}
    </>
  );
}
