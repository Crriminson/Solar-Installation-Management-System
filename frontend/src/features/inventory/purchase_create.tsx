/*
  Raise a purchase order.

  Services are left out of the picker: a labour line is not stocked, so
  ordering one from a supplier would create stock that cannot exist.
*/

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { describeError } from "../../api/client";
import Button from "../../components/Button";
import { SelectField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { fetchProductChoices } from "../catalogue/api";
import { createPurchaseOrder, fetchSuppliers } from "./api";
import styles from "./inventory.module.css";

interface DraftLine {
  product: string;
  quantity: string;
  unitCost: string;
}

const EMPTY_LINE: DraftLine = { product: "", quantity: "", unitCost: "" };

/* MAX_PAGE_SIZE in the Django settings: the most one request may hold. */
const PICKER_SIZE = 100;

export default function PurchaseCreate() {
  const navigate = useNavigate();
  const [supplier, setSupplier] = useState("");
  const [expectedOn, setExpectedOn] = useState("");
  const [invoiceReference, setInvoiceReference] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([{ ...EMPTY_LINE }]);

  /* A drop-down cannot page, so it asks for the most the server allows
     and says so if there are more, rather than silently dropping them. */
  const suppliers = useQuery({
    queryKey: ["suppliers", "picker"],
    queryFn: () => fetchSuppliers(new URLSearchParams({
      active: "true", page_size: String(PICKER_SIZE),
    })),
  });
  const products = useQuery({
    queryKey: ["product-choices"],
    queryFn: fetchProductChoices,
  });

  const mutation = useMutation({
    mutationFn: () => createPurchaseOrder({
      supplier: Number(supplier),
      expected_on: expectedOn || null,
      supplier_invoice_reference: invoiceReference,
      lines: lines
        .filter((line) => line.product && line.quantity)
        .map((line) => ({
          product: Number(line.product),
          quantity: line.quantity,
          unit_cost: line.unitCost || "0",
        })),
    }),
    onSuccess: (purchase) => navigate(`/purchasing/${purchase.id}`),
  });

  if (suppliers.isPending || products.isPending) {
    return <LoadingMessage label="Loading suppliers and products…" />;
  }
  if (suppliers.isError) {
    return <ErrorMessage error={suppliers.error} onRetry={suppliers.refetch} />;
  }
  if (products.isError) {
    return <ErrorMessage error={products.error} onRetry={products.refetch} />;
  }

  const stockable = products.data.filter(
    (product) => product.tracking_method !== "service",
  );
  const ready = supplier !== "" && lines.some((line) => line.product && line.quantity);

  function updateLine(index: number, changes: Partial<DraftLine>) {
    setLines(lines.map((line, position) =>
      position === index ? { ...line, ...changes } : line));
  }

  return <>
    <PageHeader back={{ to: "/purchasing", label: "Purchase orders" }}
      title="New purchase order"
      subtitle="Each line becomes stock when the goods arrive." />

    <div className={styles.form}>
      <SelectField label="Supplier" required value={supplier}
        options={[{ value: "", label: "Choose a supplier" },
          ...suppliers.data.results.map((row) => ({
            value: String(row.id), label: row.name,
          }))]}
        hint={suppliers.data.count > suppliers.data.results.length
          ? `Showing the first ${suppliers.data.results.length} of ${suppliers.data.count} active suppliers.`
          : undefined}
        onChange={setSupplier} />
      <TextField label="Expected delivery date" type="date" value={expectedOn}
        onChange={setExpectedOn} />
      <TextField label="Supplier invoice reference" value={invoiceReference}
        onChange={setInvoiceReference}
        hint="Optional now. Recorded once, so the same invoice cannot be entered twice." />

      <h2>Lines</h2>
      {lines.map((line, index) => <div key={index} className={styles.batchRow}>
        <SelectField label="Product" value={line.product}
          options={[{ value: "", label: "Choose a product" },
            ...stockable.map((product) => ({
              value: String(product.id),
              label: `${product.sku} · ${product.name}`,
            }))]}
          onChange={(product) => updateLine(index, { product })} />
        <TextField label="Quantity" inputMode="decimal" value={line.quantity}
          onChange={(quantity) => updateLine(index, { quantity })} />
        <TextField label="Unit cost" inputMode="decimal" value={line.unitCost}
          onChange={(unitCost) => updateLine(index, { unitCost })} />
      </div>)}

      <div className={styles.actions}>
        <Button type="button" onClick={() => setLines([...lines, { ...EMPTY_LINE }])}>
          Add line
        </Button>
        {lines.length > 1 && <Button type="button" onClick={() => setLines(lines.slice(0, -1))}>
          Remove last line
        </Button>}
      </div>

      {mutation.isError && <p className={styles.error}>{describeError(mutation.error)}</p>}
      <Button variant="primary" disabled={!ready || mutation.isPending}
        onClick={() => mutation.mutate()}>
        {mutation.isPending ? "Creating…" : "Create purchase order"}
      </Button>
    </div>
  </>;
}
