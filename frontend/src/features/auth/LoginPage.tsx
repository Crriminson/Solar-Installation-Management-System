/* Staff sign-in. Customers never reach this: they have no account. */

import { useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { describeError } from "../../api/client";
import BrandShell from "../../components/BrandShell";
import Button from "../../components/Button";
import { TextField } from "../../components/Field";
import { LoadingMessage } from "../../components/StateMessage";
import { HOME_PATH } from "../../navigation";
import { login, SESSION_QUERY_KEY, useSession } from "./session";
import styles from "./LoginPage.module.css";

/* Only a path inside this app, so a crafted link cannot send someone
   to another site straight after they sign in. */
function safeNextPath(next: string | null) {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : HOME_PATH;
}

export default function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const next = safeNextPath(params.get("next"));

  const session = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const mutation = useMutation({
    mutationFn: login,
    onSuccess: (data) => {
      queryClient.setQueryData(SESSION_QUERY_KEY, data);
      navigate(next, { replace: true });
    },
  });

  if (session.isPending) return <LoadingMessage label="Loading…" />;
  if (session.data?.user) return <Navigate to={next} replace />;

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    mutation.mutate({ username, password });
  }

  return (
    <BrandShell
      panel={
        <>
          <p className={styles.headline}>Every job, from first call to warranty.</p>
          <p className={styles.lead}>
            Enquiries, surveys and handoffs in one place, so nobody has to
            phone anyone.
          </p>
        </>
      }
    >
      <form className={styles.form} onSubmit={handleSubmit}>
        <h1 className={styles.title}>Sign in</h1>
        <p className={styles.intro}>Use your staff account.</p>

        {mutation.isError && (
          <p className={styles.error} role="alert">
            {describeError(mutation.error)}
          </p>
        )}

        <TextField
          label="Username"
          value={username}
          autoComplete="username"
          onChange={setUsername}
        />
        <TextField
          label="Password"
          type="password"
          value={password}
          autoComplete="current-password"
          onChange={setPassword}
        />

        <Button
          type="submit"
          variant="primary"
          disabled={mutation.isPending || !username || !password}
        >
          {mutation.isPending ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </BrandShell>
  );
}
