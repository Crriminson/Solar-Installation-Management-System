/*
  Adding or editing a product (F04).

  Prices are not here. They are set from the product's panel, because a
  price is a dated record and not a field to overwrite.
*/

import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { describeError, fieldErrorsFrom } from "../../api/client";
import Button from "../../components/Button";
import { SelectField, TextAreaField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { createProduct, fetchProduct, fetchWarrantyPolicies, updateProduct } from "./api";
import { CATEGORY_OPTIONS, TRACKING_OPTIONS, YES_NO_OPTIONS } from "./labels";
import type { Product } from "./types";
import styles from "./ProductForm.module.css";

const LIST_PATH = "/catalogue/products";

const EMPTY_VALUES = {
  sku: "",
  name: "",
  description: "",
  category: "",
  tracking_method: "",
  unit: "",
  stocking_quantity: "1",
  gst_rate_percent: "",
  warranty_policy: "",
  rated_power_w: "",
  storage_kwh: "",
  nominal_voltage_v: "",
  is_repair_part: "false",
  is_active: "true",
};

type Values = typeof EMPTY_VALUES;

/* Loads the product first when editing, so the form starts filled in. */
export default function ProductForm() {
  const { productId } = useParams();

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["products", "detail", productId],
    queryFn: () => fetchProduct(productId!),
    enabled: Boolean(productId),
    gcTime: 0,
  });

  if (!productId) return <Form initial={EMPTY_VALUES} />;
  if (isPending) return <LoadingMessage label="Loading product…" />;
  if (isError) return <ErrorMessage error={error} onRetry={refetch} />;

  return <Form productId={productId} revision={data.revision} initial={toValues(data)} />;
}

function Form({ productId, revision, initial }: { productId?: string; revision?: number; initial: Values }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [values, setValues] = useState(initial);
  const [sourceRevision] = useState(revision);

  const policies = useQuery({
    queryKey: ["warranty-policies"],
    queryFn: fetchWarrantyPolicies,
  });

  const mutation = useMutation({
    mutationFn: () => {
      const payload = toPayload(values);
      return productId ? updateProduct(productId, { ...payload, revision: sourceRevision }) : createProduct(payload);
    },
    onSuccess: (product) => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      navigate(`${LIST_PATH}?selected=${product.id}`);
    },
  });

  const errors = fieldErrorsFrom(mutation.error);

  function bind(name: keyof Values) {
    return {
      value: values[name],
      onChange: (value: string) =>
        setValues((current) => ({ ...current, [name]: value })),
      error: errors[name]?.[0],
    };
  }

  const canSave =
    values.sku && values.name && values.category && values.tracking_method &&
    values.unit && values.gst_rate_percent;

  return (
    <div className={styles.page}>
      <PageHeader
        back={{ to: LIST_PATH, label: "Products" }}
        title={productId ? "Edit product" : "New product"}
      />

      <form
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        {mutation.isError && (
          <p className={styles.error} role="alert">
            {Object.keys(errors).length > 0
              ? "Please correct the highlighted fields below."
              : describeError(mutation.error)}
          </p>
        )}

        <section className={styles.section}>
          <div className={styles.grid}>
            <TextField label="SKU" required {...bind("sku")} />
            <TextField label="Name" required {...bind("name")} />
            <SelectField
              label="Category"
              required
              options={CATEGORY_OPTIONS}
              placeholder="Choose one"
              {...bind("category")}
            />
            <SelectField
              label="Tracking"
              required
              options={TRACKING_OPTIONS}
              placeholder="Choose one"
              hint="Equipment is serialized. Cable and consumables go by batch."
              {...bind("tracking_method")}
            />
            <TextField
              label="Unit"
              required
              hint="Such as piece, m, set or hour."
              {...bind("unit")}
            />
            <TextField
              label="Stocked in multiples of"
              required
              inputMode="decimal"
              hint="Calculated quantities round up to this."
              {...bind("stocking_quantity")}
            />
            <TextField
              label="GST rate"
              required
              inputMode="decimal"
              unit="%"
              {...bind("gst_rate_percent")}
            />
            <SelectField
              label="Warranty policy"
              options={(policies.data ?? []).map((policy) => ({
                value: String(policy.id),
                label: policy.name,
              }))}
              placeholder="None"
              {...bind("warranty_policy")}
            />
            <TextAreaField label="Description" wide {...bind("description")} />
          </div>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Used for sizing</h2>
          <div className={styles.grid}>
            <TextField
              label="Rated power"
              inputMode="decimal"
              unit="W"
              {...bind("rated_power_w")}
            />
            <TextField
              label="Storage"
              inputMode="decimal"
              unit="kWh"
              hint="Batteries only."
              {...bind("storage_kwh")}
            />
            <TextField
              label="Nominal voltage"
              inputMode="decimal"
              unit="V"
              {...bind("nominal_voltage_v")}
            />
            <SelectField
              label="Approved repair part"
              options={YES_NO_OPTIONS}
              {...bind("is_repair_part")}
            />
            {productId && (
              <SelectField label="Active" options={YES_NO_OPTIONS} {...bind("is_active")} />
            )}
          </div>
        </section>

        <Button type="submit" variant="primary" disabled={!canSave || mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Save product"}
        </Button>
      </form>
    </div>
  );
}


// ============================================================
// Helpers
// ============================================================

function toValues(product: Product): Values {
  return {
    sku: product.sku,
    name: product.name,
    description: product.description,
    category: product.category,
    tracking_method: product.tracking_method,
    unit: product.unit,
    stocking_quantity: product.stocking_quantity,
    gst_rate_percent: product.gst_rate_percent,
    warranty_policy: product.warranty_policy ? String(product.warranty_policy) : "",
    rated_power_w: product.rated_power_w ?? "",
    storage_kwh: product.storage_kwh ?? "",
    nominal_voltage_v: product.nominal_voltage_v ?? "",
    is_repair_part: String(product.is_repair_part),
    is_active: String(product.is_active),
  };
}

/* Blank optional numbers and links are sent as null, never as "". */
function toPayload(values: Values) {
  return {
    ...values,
    warranty_policy: values.warranty_policy || null,
    rated_power_w: values.rated_power_w || null,
    storage_kwh: values.storage_kwh || null,
    nominal_voltage_v: values.nominal_voltage_v || null,
    is_repair_part: values.is_repair_part === "true",
    is_active: values.is_active === "true",
  };
}
