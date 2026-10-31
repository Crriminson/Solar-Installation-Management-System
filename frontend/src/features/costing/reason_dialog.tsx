/*
  Asks why before reversing a ledger row.

  Every reversal here says the same thing: the row stays on the ledger,
  marked reversed. Money is corrected, never erased.
*/

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { describeError } from "../../api/client";
import ConfirmDialog from "../../components/ConfirmDialog";
import { TextAreaField } from "../../components/Field";

export default function ReasonDialog({ title, onSubmit, onClose, onDone }: {
  title: string;
  onSubmit: (reason: string) => Promise<unknown>;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const mutation = useMutation({ mutationFn: () => onSubmit(reason), onSuccess: onDone });

  return <ConfirmDialog title={title} confirmLabel="Reverse" pending={mutation.isPending}
    error={mutation.isError ? describeError(mutation.error) : null}
    onConfirm={() => mutation.mutate()} onCancel={onClose}>
    <p>The row stays on the ledger, marked reversed.</p>
    <TextAreaField label="Why?" required value={reason} onChange={setReason} />
  </ConfirmDialog>;
}
