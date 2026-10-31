/*
  The channel a screen uses to confirm a completed action.

  Separate from Toast.tsx so that file exports components only, which
  is what keeps fast refresh working during development.
*/

import { createContext, useContext } from "react";

export const ToastContext = createContext<(message: string) => void>(() => {});

/* Call this to confirm a completed action: confirm("Payment cleared"). */
export function useToast() {
  return useContext(ToastContext);
}
