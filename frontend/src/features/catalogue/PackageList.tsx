/*
  Package templates (F04).

  Each row shows what quotations would use today. A package with no
  reviewed version cannot reach a customer, so that is made plain.
*/

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";

import { describeError, fieldErrorsFrom } from "../../api/client";
import Button from "../../components/Button";
import DataTable, { type Column } from "../../components/DataTable";
import { SelectField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import Pagination from "../../components/Pagination";
import SidePanel from "../../components/SidePanel";
import { EmptyMessage, ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { PACKAGE_NOT_LIVE, VERSION_STATUSES } from "../../components/status";
import { useListParams } from "../../components/useListParams";
import { formatQuantity } from "../../lib/format";
import { useStaffUser } from "../auth/session";
import { createPackage, fetchPackages } from "./api";
import { labelOf, PACKAGE_KIND_OPTIONS, SIZED_KINDS } from "./labels";
import type { PackageTemplate } from "./types";
import styles from "./PackageList.module.css";

const COLUMNS: readonly Column<PackageTemplate>[] = [
  { header: "Package", render: (template) => template.name },
  { header: "Kind", render: (template) => labelOf(PACKAGE_KIND_OPTIONS, template.kind) },
  {
    header: "Capacity",
    render: (template) =>
      template.capacity_kw ? formatQuantity(template.capacity_kw, "kW") : "–",
  },
  {
    header: "Status",
    render: (template) =>
      template.active_version_number ? (
        <StatusBadge status={VERSION_STATUSES.active} />
      ) : (
        <StatusBadge status={PACKAGE_NOT_LIVE} />
      ),
  },
  {
    header: "Version",
    render: (template) => (
      <>
        {template.active_version_number ? `Version ${template.active_version_number}` : "–"}
        {template.has_draft && <div className={styles.muted}>Draft in progress</div>}
      </>
    ),
  },
];

export default function PackageList() {
  const user = useStaffUser();
  const navigate = useNavigate();
  const list = useListParams();
  const [adding, setAdding] = useState(false);

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["packages", list.page],
    queryFn: () => fetchPackages(list.page),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title="Packages"
        subtitle="The bills of materials quotations are built from."
        actions={
          user.can_manage_catalogue && (
            <Button variant="primary" onClick={() => setAdding(true)}>
              New package
            </Button>
          )
        }
      />

      {isPending && <LoadingMessage label="Loading packages…" />}
      {isError && <ErrorMessage error={error} onRetry={refetch} />}

      {data && data.results.length === 0 && (
        <EmptyMessage>No packages yet.</EmptyMessage>
      )}

      {data && data.results.length > 0 && (
        <>
          <DataTable
            caption="Packages"
            columns={COLUMNS}
            rows={data.results}
            rowKey={(template) => template.id}
            onRowClick={(template) => navigate(`/catalogue/packages/${template.id}`)}
          />
          <Pagination page={list.page} count={data.count} onChange={list.setPage} />
        </>
      )}

      {adding && <NewPackagePanel onClose={() => setAdding(false)} />}
    </>
  );
}

function NewPackagePanel({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [kind, setKind] = useState("");
  const [capacity, setCapacity] = useState("");
  const [name, setName] = useState("");

  const isSized = SIZED_KINDS.includes(kind);

  const mutation = useMutation({
    mutationFn: () =>
      createPackage({ kind, capacity_kw: isSized ? capacity : null, name }),
    onSuccess: (template) => {
      queryClient.invalidateQueries({ queryKey: ["packages"] });
      navigate(`/catalogue/packages/${template.id}`);
    },
  });

  const errors = fieldErrorsFrom(mutation.error);

  return (
    <SidePanel label="New package" onClose={onClose}>
      <h2 className={styles.panelTitle}>New package</h2>

      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <SelectField
          label="Kind"
          required
          options={PACKAGE_KIND_OPTIONS}
          placeholder="Choose one"
          value={kind}
          onChange={setKind}
          error={errors.kind?.[0]}
        />
        {isSized && (
          <TextField
            label="Capacity"
            required
            inputMode="decimal"
            unit="kW"
            value={capacity}
            onChange={setCapacity}
            error={errors.capacity_kw?.[0]}
          />
        )}
        <TextField
          label="Name"
          required
          value={name}
          onChange={setName}
          error={errors.name?.[0]}
        />

        {mutation.isError && Object.keys(errors).length === 0 && (
          <p className={styles.error} role="alert">
            {describeError(mutation.error)}
          </p>
        )}

        <Button
          type="submit"
          variant="primary"
          disabled={!kind || !name || (isSized && !capacity) || mutation.isPending}
        >
          {mutation.isPending ? "Saving…" : "Create package"}
        </Button>
      </form>
    </SidePanel>
  );
}
