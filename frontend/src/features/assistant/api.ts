/* The staff assistant (F21). Questions are answered from the notes. */

import { apiGet, apiStream } from "../../api/client";

export interface AssistantStatus {
  ready: boolean;
  problem: string;
}

export interface Source {
  title: string;
  heading: string;
  url: string;
  checked_on: string;
}

export interface Turn {
  role: "user" | "assistant";
  content: string;
}

type AnswerEvent =
  | { type: "sources"; sources: Source[] }
  | { type: "token"; text: string }
  | { type: "done" }
  | { type: "error"; message: string };

export function fetchStatus() {
  return apiGet<AssistantStatus>("assistant/status/");
}

/* Calls back for each event as it arrives, so words show as they are written. */
export async function askQuestion(
  question: string,
  history: Turn[],
  signal: AbortSignal,
  onEvent: (event: AnswerEvent) => void,
) {
  const response = await apiStream("assistant/ask/", { question, history }, signal);
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let pending = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;

    // One read can end halfway through a line, or through a character.
    pending += decoder.decode(value, { stream: true });
    const lines = pending.split("\n");
    pending = lines.pop() ?? "";

    for (const line of lines) {
      if (line) onEvent(JSON.parse(line) as AnswerEvent);
    }
  }
}
