/*
  One package and its versions (F04).

  Only a draft can change. Going live is a review by an administrator,
  and it locks that version for good, because a quotation built from it
  has to stay reproducible. Any later change is a new version.
*/

import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, describeError, fieldErrorsFrom } from "../../api/client";
import Button from "../../components/Button";
import ConfirmDialog from "../../components/ConfirmDialog";
import DataTable, { type Column } from "../../components/DataTable";
import { SelectField, TextField } from "../../components/Field";
import FilterTabs from "../../components/FilterTabs";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import { EmptyMessage, ErrorMessage, LoadingRecord } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { PACKAGE_NOT_LIVE, VERSION_STATUSES } from "../../components/status";
import { useToast } from "../../components/ToastContext";
import { formatDateTime, formatQuantity } from "../../lib/format";
import { useStaffUser } from "../auth/session";
import {
  activateVersion,
  addLine,
  fetchPackage,
  fetchProductChoices,
  removeLine,
  startVersion,
  updateVersion,
} from "./api";
import { BASIS_OPTIONS, labelOf, PACKAGE_KIND_OPTIONS } from "./labels";
import type { PackageLine, PackageTemplateDetail, PackageVersion } from "./types";
import styles from "./PackageRecord.module.css";

export default function PackageRecord() {
  const { packageId = "" } = useParams();
  const [params, setParams] = useSearchParams();

  const { data: template, isPending, isError, error, refetch } = useQuery({
    queryKey: ["packages", "detail", packageId],
    queryFn: () => fetchPackage(packageId),
  });

  if (isPending) return <LoadingRecord label="Loading package…" />;
  if (isError) return <ErrorMessage error={error} onRetry={refetch} />;

  const chosen = params.get("version");
  const shown =
    template.versions.find((version) => String(version.version_number) === chosen) ??
    template.versions[0];

  const tabs = template.versions.map((version) => ({
    key: String(version.version_number),
    label: `Version ${version.version_number}`,
  }));

  return (
    <>
      <PageHeader
        back={{ to: "/catalogue/packages", label: "Packages" }}
        title={template.name}
        subtitle={labelOf(PACKAGE_KIND_OPTIONS, template.kind)}
        actions={<HeaderActions template={template} shown={shown} />}
      >
        <div className={styles.summary}>
          <StatusBadge
            status={template.active_version_number ? VERSION_STATUSES.active : PACKAGE_NOT_LIVE}
          />
          <span className={styles.muted}>
            {template.active_version_number
              ? `Quotations use version ${template.active_version_number}`
              : "Cannot be quoted until a version is reviewed"}
          </span>
        </div>
      </PageHeader>

      {!shown && <EmptyMessage>No version yet. Start one to add its parts.</EmptyMessage>}

      {shown && (
        <>
          {tabs.length > 1 && (
            <FilterTabs
              label="Versions"
              options={tabs}
              value={String(shown.version_number)}
              onChange={(version) => setParams({ version }, { replace: true })}
            />
          )}
          {/* Keyed, so forms start clean for each version. */}
          <VersionDetail key={shown.id} version={shown} />
        </>
      )}
    </>
  );
}


// ============================================================
// Header actions
// ============================================================

function HeaderActions({
  template,
  shown,
}: {
  template: PackageTemplateDetail;
  shown: PackageVersion | undefined;
}) {
  const user = useStaffUser();
  const queryClient = useQueryClient();

  const start = useMutation({
    mutationFn: () => startVersion(template.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["packages"] }),
  });

  const canStart = user.can_manage_catalogue && !template.has_draft;
  const canReview = user.can_review_packages && shown?.is_editable;

  return (
    <>
      {canStart && (
        <Button
          variant={template.versions.length === 0 ? "primary" : "secondary"}
          disabled={start.isPending}
          onClick={() => start.mutate()}
        >
          {template.versions.length === 0 ? "Start first version" : "Start new version"}
        </Button>
      )}
      {canReview && shown && <ReviewAction template={template} version={shown} />}
      {start.isError && (
        <p className={styles.error} role="alert">
          {describeError(start.error)}
        </p>
      )}
    </>
  );
}

function ReviewAction({
  template,
  version,
}: {
  template: PackageTemplateDetail;
  version: PackageVersion;
}) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const confirm = useToast();

  const mutation = useMutation({
    mutationFn: () => activateVersion(version.id, version.revision),
    onSuccess: () => {
      setConfirming(false);
      confirm(`${template.name} version ${version.version_number} is live`);
      queryClient.invalidateQueries({ queryKey: ["packages"] });
    },
  });

  const problems = problemsFrom(mutation.error);

  return (
    <>
      <Button variant="primary" onClick={() => setConfirming(true)}>
        Review and take live
      </Button>

      {confirming && (
        <ConfirmDialog
          title={`Take ${template.name} version ${version.version_number} live?`}
          confirmLabel="Take live"
          pending={mutation.isPending}
          error={problems.length === 0 && mutation.isError ? describeError(mutation.error) : null}
          onConfirm={() => mutation.mutate()}
          onCancel={() => {
            setConfirming(false);
            mutation.reset();
          }}
        >
          Quotations will use this version, and it can no longer be changed.
          {template.active_version_number &&
            ` Version ${template.active_version_number} is retired.`}
          {problems.length > 0 && (
            <ul className={styles.problems} role="alert">
              {problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          )}
        </ConfirmDialog>
      )}
    </>
  );
}


// ============================================================
// One version
// ============================================================

function VersionDetail({ version }: { version: PackageVersion }) {
  const user = useStaffUser();
  const canEdit = version.is_editable && user.can_manage_catalogue;

  const columns: Column<PackageLine>[] = [
    { header: "SKU", render: (line) => <Reference>{line.sku}</Reference> },
    { header: "Product", render: (line) => line.product_name },
    { header: "Quantity", render: (line) => describeQuantity(line) },
  ];
  if (canEdit) {
    columns.push({ header: "", render: (line) => <RemoveLine line={line} revision={version.revision} /> });
  }

  return (
    <>
      <div className={styles.versionHead}>
        <StatusBadge status={VERSION_STATUSES[version.status]} />
        {version.reviewed_at && (
          <span className={styles.muted}>
            Reviewed {formatDateTime(version.reviewed_at)}, {version.reviewed_by_name}
          </span>
        )}
      </div>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Sizing figures</h2>
        {canEdit ? <SizingForm version={version} /> : <SizingFacts version={version} />}
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Parts</h2>
        {version.lines.length === 0 ? (
          <EmptyMessage>No parts on this version yet.</EmptyMessage>
        ) : (
          <DataTable
            caption="Parts"
            columns={columns}
            rows={version.lines}
            rowKey={(line) => line.id}
          />
        )}
        {canEdit && <AddLineForm version={version} />}
      </section>
    </>
  );
}

function SizingFacts({ version }: { version: PackageVersion }) {
  return (
    <dl className={styles.facts}>
      <dt>Cable waste factor</dt>
      <dd>× {Number(version.cable_waste_factor)}</dd>
      <dt>Termination buffer</dt>
      <dd>{formatQuantity(version.cable_termination_buffer_m, "m")}</dd>
      {version.battery_depth_of_discharge && (
        <>
          <dt>Battery depth of discharge</dt>
          <dd>{Number(version.battery_depth_of_discharge)}</dd>
        </>
      )}
    </dl>
  );
}

function SizingForm({ version }: { version: PackageVersion }) {
  const queryClient = useQueryClient();
  const [waste, setWaste] = useState(version.cable_waste_factor);
  const [buffer, setBuffer] = useState(version.cable_termination_buffer_m);
  const [depth, setDepth] = useState(version.battery_depth_of_discharge ?? "");
  const [revision, setRevision] = useState(version.revision);

  const mutation = useMutation({
    mutationFn: () =>
      updateVersion(version.id, {
        revision,
        cable_waste_factor: waste,
        cable_termination_buffer_m: buffer,
        battery_depth_of_discharge: depth || null,
      }),
    onSuccess: (updated) => { setRevision(updated.revision); queryClient.invalidateQueries({ queryKey: ["packages"] }); },
  });

  const errors = fieldErrorsFrom(mutation.error);

  return (
    <form
      className={styles.inlineForm}
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate();
      }}
    >
      <TextField
        label="Cable waste factor"
        inputMode="decimal"
        unit="×"
        value={waste}
        onChange={setWaste}
        error={errors.cable_waste_factor?.[0]}
      />
      <TextField
        label="Termination buffer"
        inputMode="decimal"
        unit="m"
        value={buffer}
        onChange={setBuffer}
        error={errors.cable_termination_buffer_m?.[0]}
      />
      <TextField
        label="Battery depth of discharge"
        inputMode="decimal"
        hint="Off-grid only, such as 0.8."
        value={depth}
        onChange={setDepth}
        error={errors.battery_depth_of_discharge?.[0]}
      />
      <Button type="submit" disabled={mutation.isPending}>
        {mutation.isPending ? "Saving…" : "Save figures"}
      </Button>
    </form>
  );
}

function AddLineForm({ version }: { version: PackageVersion }) {
  const queryClient = useQueryClient();
  const [product, setProduct] = useState("");
  const [basis, setBasis] = useState("fixed");
  const [quantity, setQuantity] = useState("");

  const choices = useQuery({
    queryKey: ["products", "choices"],
    queryFn: fetchProductChoices,
  });

  const isFixed = basis === "fixed";

  const mutation = useMutation({
    mutationFn: () =>
      addLine(version.id, {
        revision: version.revision,
        product: Number(product),
        basis,
        quantity: isFixed ? quantity : null,
        notes: "",
      }),
    onSuccess: () => {
      setProduct("");
      setQuantity("");
      queryClient.invalidateQueries({ queryKey: ["packages"] });
    },
  });

  // Each product appears once on a version, so used ones are not offered.
  const used = new Set(version.lines.map((line) => line.product));
  const options = (choices.data ?? [])
    .filter((choice) => !used.has(choice.id))
    .map((choice) => ({ value: String(choice.id), label: `${choice.sku} ${choice.name}` }));

  return (
    <form
      className={styles.addLine}
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate();
      }}
    >
      <h3 className={styles.addLineTitle}>Add a part</h3>

      <div className={styles.inlineForm}>
        <SelectField
          label="Product"
          options={options}
          placeholder="Choose one"
          value={product}
          onChange={setProduct}
        />
        <SelectField
          label="Quantity comes from"
          options={BASIS_OPTIONS}
          value={basis}
          onChange={setBasis}
        />
        {isFixed && (
          <TextField
            label="Quantity"
            inputMode="decimal"
            value={quantity}
            onChange={setQuantity}
          />
        )}
        <Button
          type="submit"
          disabled={!product || (isFixed && !quantity) || mutation.isPending}
        >
          {mutation.isPending ? "Adding…" : "Add part"}
        </Button>
      </div>

      {mutation.isError && (
        <p className={styles.error} role="alert">
          {describeError(mutation.error)}
        </p>
      )}
    </form>
  );
}

function RemoveLine({ line, revision }: { line: PackageLine; revision: number }) {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => removeLine(line.id, revision),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["packages"] }),
  });

  return (
    <Button
      disabled={mutation.isPending}
      aria-label={`Remove ${line.sku}`}
      onClick={() => mutation.mutate()}
    >
      Remove
    </Button>
  );
}


// ============================================================
// Helpers
// ============================================================

function describeQuantity(line: PackageLine) {
  if (line.basis === "cable_route") return "From the surveyed cable route";
  if (line.basis === "battery_load") return "From the off-grid load and backup";
  return line.quantity ? formatQuantity(line.quantity, line.unit) : "–";
}

/* The API lists everything stopping a version going live. */
function problemsFrom(error: unknown): string[] {
  if (!(error instanceof ApiError)) return [];

  const details = error.details as { problems?: string[] } | null;
  return details?.problems ?? [];
}
