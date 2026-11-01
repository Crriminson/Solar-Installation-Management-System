/*
  One conversation with the assistant.

  Nothing is stored on the server, so the conversation lives in the tab.
  It survives moving to another screen and back, because a technician
  will check a job and return to their question. It is kept per person,
  so handing a shared tablet over does not hand over the chat.
*/

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, describeError } from "../../api/client";
import { askQuestion, type Source, type Turn } from "./api";

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  sources: Source[];
  failed?: boolean;
}

/* What the server accepts, and what a follow-up needs. */
const HISTORY_TURNS = 4;

function storageKey(userId: number) {
  return `assistant-chat-${userId}`;
}

function restore(userId: number): ChatMessage[] {
  try {
    return JSON.parse(sessionStorage.getItem(storageKey(userId)) ?? "[]") as ChatMessage[];
  } catch {
    return [];
  }
}

function remember(userId: number, messages: ChatMessage[]) {
  try {
    sessionStorage.setItem(storageKey(userId), JSON.stringify(messages));
  } catch {
    // Blocked storage only costs the conversation on the way back.
  }
}

function asHistory(messages: ChatMessage[]): Turn[] {
  return messages
    .filter((message) => !message.failed && message.text)
    .slice(-HISTORY_TURNS)
    .map((message) => ({ role: message.role, content: message.text }));
}

/* A 503 carries a sentence meant for this person; describeError would
   replace it with the general apology. */
function explain(error: unknown) {
  if (error instanceof ApiError && error.status === 503) {
    const details = error.details as { detail?: string } | null;
    if (details?.detail) return details.detail;
  }
  return describeError(error);
}

export function useChat(userId: number) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => restore(userId));
  const [asking, setAsking] = useState(false);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!asking) remember(userId, messages);
  }, [userId, messages, asking]);

  // Leaving the screen frees the model for whoever asks next.
  useEffect(() => () => controller.current?.abort(), []);

  const ask = useCallback(async (question: string) => {
    const history = asHistory(messages);
    const now = Date.now();
    const answerId = now + 1;

    function updateAnswer(change: (answer: ChatMessage) => ChatMessage) {
      setMessages((current) => current.map(
        (message) => (message.id === answerId ? change(message) : message),
      ));
    }

    setMessages((current) => [
      ...current,
      { id: now, role: "user", text: question, sources: [] },
      { id: answerId, role: "assistant", text: "", sources: [] },
    ]);
    setAsking(true);
    controller.current = new AbortController();

    try {
      await askQuestion(question, history, controller.current.signal, (event) => {
        if (event.type === "sources") {
          updateAnswer((answer) => ({ ...answer, sources: event.sources }));
        } else if (event.type === "token") {
          updateAnswer((answer) => ({ ...answer, text: answer.text + event.text }));
        } else if (event.type === "error") {
          updateAnswer((answer) => ({ ...answer, failed: true, text: event.message }));
        }
      });
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        updateAnswer((answer) => ({ ...answer, failed: true, text: explain(error) }));
      }
    } finally {
      setAsking(false);
    }
  }, [messages]);

  const stop = useCallback(() => controller.current?.abort(), []);

  const clear = useCallback(() => setMessages([]), []);

  return { messages, asking, ask, stop, clear };
}
