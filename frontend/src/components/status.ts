/*
  The status system from design.md section 7.

  Every state in the spec maps to one of six tones, so "waiting" looks
  the same on an enquiry as it will on a ticket. Red means someone must
  act now, which is why Lost is Closed and not Blocked: that work is over.
*/

export type Tone = "neutral" | "active" | "waiting" | "blocked" | "done" | "closed";

/* Shape as well as colour, because colour alone fails WCAG 1.4.1. */
export const TONE_SHAPES: Record<Tone, string> = {
  neutral: "○",
  active: "◐",
  waiting: "◆",
  blocked: "▲",
  done: "●",
  closed: "✕",
};

export interface StatusInfo {
  label: string;
  tone: Tone;
}

export const ENQUIRY_STATUSES: Record<string, StatusInfo> = {
  new: { label: "New", tone: "neutral" },
  contacting: { label: "Contacting", tone: "active" },
  qualified: { label: "Qualified", tone: "active" },
  survey_scheduled: { label: "Survey scheduled", tone: "waiting" },
  lost: { label: "Lost", tone: "closed" },
};
