/* Sales selects an approved survey and payment terms; the server generates every component. */

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { describeError, fieldErrorsFrom } from "../../api/client";
import Button from "../../components/Button";
import { SelectField, TextAreaField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import SearchInput from "../../components/SearchInput";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { fetchSurveys } from "../surveys/api";
import { fetchQuotation, generateQuotation } from "./api";
import type { Quotation } from "./types";
import styles from "./quotations.module.css";

const ELIGIBILITY_OPTIONS = [{ value: "", label: "Not confirmed" }, { value: "yes", label: "Yes" }, { value: "no", label: "No" }];

export default function QuotationGenerate() {
  const [params] = useSearchParams();
  const previousId = params.get("previous");
  const previous = useQuery({ queryKey: ["quotations", previousId], queryFn: () => fetchQuotation(previousId!), enabled: Boolean(previousId) });
  if (previousId && previous.isPending) return <LoadingMessage label="Loading source quotation…" />;
  if (previousId && previous.isError) return <ErrorMessage error={previous.error} onRetry={previous.refetch} />;
  return <QuotationGenerationForm key={previousId ?? "new"} previous={previous.data} />;
}


function QuotationGenerationForm({ previous }: { previous?: Quotation }) {
  const [params] = useSearchParams();
  const [sourcePrevious] = useState(previous);
  const previousId = sourcePrevious?.id;
  const [search, setSearch] = useState("");
  const surveys = useQuery({ queryKey: ["surveys", "approved", search], queryFn: () => fetchSurveys({ approved: true, search }) });
  const [enquiry, setEnquiry] = useState(params.get("enquiry") ?? "");
  const siteState = sourcePrevious?.snapshot.site.state ?? surveys.data?.results.find((survey) => String(survey.enquiry) === enquiry)?.site_state;
  const [plan, setPlan] = useState("advance");
  const [advance, setAdvance] = useState("");
  const [notes, setNotes] = useState("");
  const [beneficiary, setBeneficiary] = useState("");
  const [category, setCategory] = useState("");
  const request = useRef<{ payload: string; key: string } | null>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => {
      const facts: Record<string, boolean> = {};
      if (beneficiary) facts.rajasthan_beneficiary = beneficiary === "yes";
      if (category) facts.sc_st_eligible = category === "yes";
      const values = { enquiry: Number(enquiry || sourcePrevious?.enquiry), payment_plan: plan,
        ...(advance && plan === "advance" ? { advance_percent: advance } : {}), terms_notes: notes, subsidy_facts: facts,
        ...(sourcePrevious ? { previous_revision: sourcePrevious.id, revision: sourcePrevious.revision } : {}) };
      const payload = JSON.stringify(values);
      if (request.current?.payload !== payload) request.current = { payload, key: crypto.randomUUID() };
      return generateQuotation({ ...values, idempotency_key: request.current!.key });
    },
    onSuccess: (quote) => { queryClient.invalidateQueries({ queryKey: ["quotations"] }); navigate(`/quotations/${quote.id}`); },
  });
  const errors = fieldErrorsFrom(mutation.error);

  return <>
    <PageHeader back={{ to: "/quotations", label: "Quotations" }} title={previousId ? "Generate revised quotation" : "Generate quotation"}
      subtitle="The backend uses the latest approved survey, reviewed package, dated prices and measured quantities." />
    <form className={styles.form} onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
      {!previousId && <>
        <SearchInput label="Find an approved survey" value={search} onSearch={setSearch} />
        {surveys.isPending && <LoadingMessage label="Loading approved surveys…" />}
        {surveys.isError && <ErrorMessage error={surveys.error} onRetry={surveys.refetch} />}
        <SelectField label="Approved survey" value={enquiry} onChange={setEnquiry} placeholder="Choose a customer and survey"
          error={errors.enquiry?.[0] ?? errors.survey?.[0]} options={(surveys.data?.results ?? []).map((survey) => ({ value: String(survey.enquiry), label: `${survey.enquiry_reference} · ${survey.customer_name}` }))} />
      </>}
      {sourcePrevious && <p>{sourcePrevious.reference} · Revision {sourcePrevious.revision_number}. Fresh acceptance is required after reissue.</p>}
      <SelectField label="Payment plan" value={plan} onChange={setPlan} options={[{ value: "advance", label: "Advance, balance due on delivery" }, { value: "full", label: "Full payment before dispatch" }]} />
      {plan === "advance" && <TextField label="Advance percentage" hint="Leave blank to use the configured default." inputMode="decimal" unit="%" value={advance} onChange={setAdvance} error={errors.advance_percent?.[0]} />}
      <TextAreaField label="Payment terms and notes" value={notes} onChange={setNotes} error={errors.terms_notes?.[0]} />
      {(siteState === "Rajasthan" || siteState === "West Bengal") && <fieldset className={styles.eligibility}>
        <legend>Conditional subsidy eligibility</legend>
        <p>Confirm these only where relevant to the site's state. An unknown required condition blocks a partial estimate.</p>
        {siteState === "Rajasthan" && <SelectField label="Rajasthan: Mukhyamantri Nishulk Bijli Yojana beneficiary" value={beneficiary} onChange={setBeneficiary} options={ELIGIBILITY_OPTIONS} />}
        {siteState === "West Bengal" && <SelectField label="West Bengal: eligible SC/ST category" value={category} onChange={setCategory} options={ELIGIBILITY_OPTIONS} />}
      </fieldset>}
      {mutation.isError && <div role="alert" className={styles.error}>{errors.package?.length ? errors.package.map((message) => <p key={message}>{message}</p>) : describeError(mutation.error)}</div>}
      <Button type="submit" variant="primary" disabled={mutation.isPending || !(enquiry || sourcePrevious)}>
        {mutation.isPending ? "Generating…" : "Generate draft"}
      </Button>
    </form>
  </>;
}
