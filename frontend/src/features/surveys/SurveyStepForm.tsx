/*
  Recording a survey on a phone (F03).

  One section at a time, so it can be filled in on a roof. Back keeps
  everything, and the last step reviews it before saving a draft. Photos
  are added to the saved draft, so a poor connection cannot cost the
  measurements as well. Offline sync is out of scope: if the connection
  drops, the values stay on screen to retry.
*/

import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { describeError, fieldErrorsFrom, type FieldErrors } from "../../api/client";
import Button from "../../components/Button";
import { SelectField, TextAreaField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import { dateTimeInputToIso, formatDateTime, formatQuantity, nowForDateTimeInput } from "../../lib/format";
import { createRevision } from "./api";
import {
  GRID_SUITABLE_OPTIONS,
  labelFor,
  ORIENTATION_OPTIONS,
  ROOF_TYPE_OPTIONS,
  SYSTEM_TYPE_OPTIONS,
} from "./labels";
import type { MeasurementValues } from "./types";
import styles from "./SurveyStepForm.module.css";

type FieldName = keyof MeasurementValues;

const EMPTY_VALUES: MeasurementValues = {
  roof_type: "",
  roof_length_m: "",
  roof_width_m: "",
  usable_area_sqm: "",
  orientation: "",
  tilt_degrees: "",
  shading_notes: "",
  cable_distance_m: "",
  cable_route_notes: "",
  site_access_notes: "",
  grid_connection_number: "",
  sanctioned_load_kw: "",
  grid_suitable: "true",
  grid_notes: "",
  recommended_system_type: "",
  recommended_capacity_kw: "",
  critical_load_kw: "",
  backup_duration_hours: "",
  surveyed_at: "",
};

/* Each step, with the fields needed before moving on. */
const STEPS: readonly { title: string; fields: readonly FieldName[]; required: readonly FieldName[] }[] = [
  {
    title: "Roof",
    fields: ["surveyed_at", "roof_type", "roof_length_m", "roof_width_m", "usable_area_sqm"],
    required: ["surveyed_at", "roof_type", "roof_length_m", "roof_width_m", "usable_area_sqm"],
  },
  {
    title: "Sun and shade",
    fields: ["orientation", "tilt_degrees", "shading_notes"],
    required: ["orientation", "tilt_degrees"],
  },
  {
    title: "Cable and access",
    fields: ["cable_distance_m", "cable_route_notes", "site_access_notes"],
    required: ["cable_distance_m"],
  },
  {
    title: "Grid",
    fields: ["grid_connection_number", "sanctioned_load_kw", "grid_suitable", "grid_notes"],
    required: [],
  },
  {
    title: "Recommendation",
    fields: [
      "recommended_system_type",
      "recommended_capacity_kw",
      "critical_load_kw",
      "backup_duration_hours",
    ],
    required: ["recommended_system_type", "recommended_capacity_kw"],
  },
];

const REVIEW_STEP = STEPS.length;
const TOTAL_STEPS = STEPS.length + 1;

/* Errors that belong to the whole revision, not one field. */
const GENERAL_ERROR_FIELD = "non_field_errors";

export default function SurveyStepForm() {
  const { surveyId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [values, setValues] = useState<MeasurementValues>({
    ...EMPTY_VALUES,
    surveyed_at: nowForDateTimeInput(),
  });
  const [step, setStep] = useState(0);

  const mutation = useMutation({
    mutationFn: () => createRevision(surveyId, toPayload(values)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["surveys"] });
      navigate(`/surveys/${surveyId}`, { replace: true });
    },
    // Takes the technician back to the step that needs fixing.
    onError: (error) => {
      const stepWithError = firstStepWithError(fieldErrorsFrom(error));
      if (stepWithError !== null) setStep(stepWithError);
    },
  });

  const errors = fieldErrorsFrom(mutation.error);
  const offGrid = values.recommended_system_type === "off_grid";

  function bind(name: FieldName) {
    return {
      value: values[name],
      onChange: (value: string) =>
        setValues((current) => ({ ...current, [name]: value })),
      error: errors[name]?.[0],
    };
  }

  const isReview = step === REVIEW_STEP;
  const required = isReview ? [] : stepRequirements(step, offGrid);
  const canContinue = required.every((name) => values[name].trim() !== "");

  return (
    <div className={styles.page}>
      <PageHeader
        back={{ to: `/surveys/${surveyId}`, label: "Survey" }}
        title={isReview ? "Check and save" : STEPS[step].title}
        subtitle={`${step + 1} of ${TOTAL_STEPS}`}
      />

      <progress className={styles.progress} value={step + 1} max={TOTAL_STEPS} aria-hidden="true" />

      {mutation.isError && (
        <p className={styles.error} role="alert">
          {errors[GENERAL_ERROR_FIELD]?.[0] ?? describeError(mutation.error)}
        </p>
      )}

      <div className={styles.fields}>
        {step === 0 && (
          <>
            <TextField label="On site at" required type="datetime-local" {...bind("surveyed_at")} />
            <SelectField
              label="Roof type"
              required
              options={ROOF_TYPE_OPTIONS}
              placeholder="Choose one"
              {...bind("roof_type")}
            />
            <TextField label="Roof length" required inputMode="decimal" unit="m" {...bind("roof_length_m")} />
            <TextField label="Roof width" required inputMode="decimal" unit="m" {...bind("roof_width_m")} />
            <TextField
              label="Usable area"
              required
              inputMode="decimal"
              unit="m²"
              hint="Free of shade for most of the day."
              {...bind("usable_area_sqm")}
            />
          </>
        )}

        {step === 1 && (
          <>
            <SelectField
              label="Roof faces"
              required
              options={ORIENTATION_OPTIONS}
              placeholder="Choose one"
              {...bind("orientation")}
            />
            <TextField
              label="Tilt"
              required
              inputMode="decimal"
              unit="°"
              hint="0 is flat, 90 is vertical."
              {...bind("tilt_degrees")}
            />
            <TextAreaField
              label="Shading"
              hint="Trees, water tanks, neighbouring buildings."
              {...bind("shading_notes")}
            />
          </>
        )}

        {step === 2 && (
          <>
            <TextField
              label="Cable route"
              required
              inputMode="decimal"
              unit="m"
              hint="Measured along the route, array to inverter, not a straight line."
              {...bind("cable_distance_m")}
            />
            <TextAreaField label="Route notes" {...bind("cable_route_notes")} />
            <TextAreaField
              label="Site access"
              hint="Stairs, lift, crane needed, parking."
              {...bind("site_access_notes")}
            />
          </>
        )}

        {step === 3 && (
          <>
            <TextField label="Grid connection number" {...bind("grid_connection_number")} />
            <TextField
              label="Sanctioned load"
              inputMode="decimal"
              unit="kW"
              {...bind("sanctioned_load_kw")}
            />
            <SelectField
              label="Grid connection"
              options={GRID_SUITABLE_OPTIONS}
              {...bind("grid_suitable")}
            />
            <TextAreaField label="Grid notes" {...bind("grid_notes")} />
          </>
        )}

        {step === 4 && (
          <>
            <SelectField
              label="System type"
              required
              options={SYSTEM_TYPE_OPTIONS}
              placeholder="Choose one"
              {...bind("recommended_system_type")}
            />
            <TextField
              label="Advisory capacity"
              required
              inputMode="decimal"
              unit="kW"
              hint="Advisory until approved. Not a certified design."
              {...bind("recommended_capacity_kw")}
            />
            {/* Battery size can never be inferred from panel capacity,
                so off-grid must carry these two figures. */}
            {offGrid && (
              <>
                <TextField
                  label="Critical load"
                  required
                  inputMode="decimal"
                  unit="kW"
                  {...bind("critical_load_kw")}
                />
                <TextField
                  label="Backup duration"
                  required
                  inputMode="decimal"
                  unit="hours"
                  {...bind("backup_duration_hours")}
                />
              </>
            )}
          </>
        )}

        {isReview && <ReviewSummary values={values} />}
      </div>

      <div className={styles.actions}>
        {step > 0 && (
          <Button onClick={() => setStep(step - 1)} disabled={mutation.isPending}>
            Back
          </Button>
        )}

        {isReview ? (
          <Button
            variant="primary"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Saving…" : "Save draft"}
          </Button>
        ) : (
          <Button variant="primary" disabled={!canContinue} onClick={() => setStep(step + 1)}>
            Next
          </Button>
        )}
      </div>
    </div>
  );
}


// ============================================================
// Helpers
// ============================================================

function ReviewSummary({ values }: { values: MeasurementValues }) {
  return (
    <dl className={styles.summary}>
      <dt>On site</dt>
      <dd>{formatDateTime(dateTimeInputToIso(values.surveyed_at))}</dd>
      <dt>Roof</dt>
      <dd>
        {labelFor(ROOF_TYPE_OPTIONS, values.roof_type)},{" "}
        {formatQuantity(values.roof_length_m, "m")} ×{" "}
        {formatQuantity(values.roof_width_m, "m")}
      </dd>
      <dt>Usable area</dt>
      <dd>{formatQuantity(values.usable_area_sqm, "m²")}</dd>
      <dt>Faces</dt>
      <dd>
        {labelFor(ORIENTATION_OPTIONS, values.orientation)}, tilt {Number(values.tilt_degrees)}°
      </dd>
      <dt>Cable route</dt>
      <dd>{formatQuantity(values.cable_distance_m, "m")}</dd>
      <dt>Grid</dt>
      <dd>{labelFor(GRID_SUITABLE_OPTIONS, values.grid_suitable)}</dd>
      <dt>Recommends</dt>
      <dd>
        {labelFor(SYSTEM_TYPE_OPTIONS, values.recommended_system_type)},{" "}
        {formatQuantity(values.recommended_capacity_kw, "kW")}
      </dd>
    </dl>
  );
}

function stepRequirements(step: number, offGrid: boolean): readonly FieldName[] {
  const { required } = STEPS[step];
  const isRecommendation = step === STEPS.length - 1;

  return isRecommendation && offGrid
    ? [...required, "critical_load_kw", "backup_duration_hours"]
    : required;
}

/* Blank optional numbers are left out rather than sent as "". */
function toPayload(values: MeasurementValues) {
  const entries = Object.entries(values).filter(([, value]) => value !== "");

  return {
    ...Object.fromEntries(entries),
    surveyed_at: dateTimeInputToIso(values.surveyed_at),
  };
}

function firstStepWithError(errors: FieldErrors) {
  const index = STEPS.findIndex((step) =>
    step.fields.some((field) => errors[field]),
  );
  return index === -1 ? null : index;
}
