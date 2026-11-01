/*
  F19 on a record: make the document, then download it.

  Generating is idempotent, so pressing it twice gives the same file
  rather than a second one. The download is the stored file, never a
  fresh render: the customer and the office must be looking at the same
  bytes.
*/

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { describeError } from "../../api/client";
import Button from "../../components/Button";
import { useToast } from "../../components/ToastContext";
import { DownloadIcon, PdfIcon } from "../../design/icons";
import { downloadUrl, fetchDocuments, generateDocument, type DocumentKind } from "./api";

export default function DocumentActions({
  kind,
  recordId,
  label,
}: {
  kind: DocumentKind;
  recordId: number;
  label: string;
}) {
  const confirm = useToast();
  const queryClient = useQueryClient();

  const documents = useQuery({
    queryKey: ["documents", kind, recordId],
    queryFn: () => fetchDocuments(kind, recordId),
  });

  const generate = useMutation({
    mutationFn: () => generateDocument(kind, recordId),
    onSuccess: () => {
      confirm(`${label} ready`);
      queryClient.invalidateQueries({ queryKey: ["documents", kind, recordId] });
    },
  });

  const existing = documents.data?.results?.[0];

  if (existing) {
    return (
      <Button
        icon={<DownloadIcon aria-hidden />}
        onClick={() => window.open(downloadUrl(existing.id), "_blank")}
      >
        {label}
      </Button>
    );
  }

  return (
    <>
      <Button
        icon={<PdfIcon aria-hidden />}
        loading={generate.isPending}
        onClick={() => generate.mutate()}
      >
        Make the {label.toLowerCase()}
      </Button>
      {generate.isError && <span>{describeError(generate.error)}</span>}
    </>
  );
}
