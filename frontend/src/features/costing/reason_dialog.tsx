/*
  Asks why before reversing a ledger row.

  Every reversal here says the same thing: the row stays on the ledger,
  marked reversed. Money is corrected, never erased.

  The confirmation is required so that no reversal lands silently.
*/

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { describeError } from "../../api/client";
import ConfirmDialog from "../../components/ConfirmDialog";
import { TextAreaField } from "../../components/Field";
import { useToast } from "../../components/ToastContext";

export default function ReasonDialog({ title, confirmation, onSubmit, onClose, onDone }: {
  title: string;
  confirmation: string;
  onSubmit: (reason: string) => Promise<unknown>;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const confirm = useToast();
  const mutation = useMutation({
    mutationFn: () => onSubmit(reason),
    onSuccess: () => { confirm(confirmation); onDone(); },
  });

  return <ConfirmDialog title={title} confirmLabel="Reverse" pending={mutation.isPending}
    error={mutation.isError ? describeError(mutation.error) : null}
    onConfirm={() => mutation.mutate()} onCancel={onClose}>
    <p>The row stays on the ledger, marked reversed.</p>
    <TextAreaField label="Why?" required value={reason} onChange={setReason} />
  </ConfirmDialog>;
}
