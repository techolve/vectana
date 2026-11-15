"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";

import { api, hasToken, setAfterLogin, type Me } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field";

type ClientInfo = { client_name: string; redirect_host: string };
type Scope = "read" | "write";

/** Asks the signed-in user to let an OAuth client (e.g. a claude.ai
 *  connector) use Vectana as them. Signs them in first if needed. */
export function OAuthConsent() {
  const t = useTranslations("oauth");
  const locale = useLocale();
  const params = useSearchParams();
  const clientId = params.get("client_id") ?? "";
  const requested = (params.get("scope") ?? "").split(" ");
  const [client, setClient] = useState<ClientInfo | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [scope, setScope] = useState<Scope>(
    requested.includes("read") && !requested.includes("write") ? "read" : "write",
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!hasToken()) {
      setAfterLogin(window.location.pathname + window.location.search);
      window.location.replace(`/${locale}/login/`);
      return;
    }
    if (!clientId) return;
    api<ClientInfo>(`/oauth/clients/${encodeURIComponent(clientId)}`, { auth: false })
      .then(setClient)
      .catch(() => setError(t("invalid")));
    api<Me>("/auth/me").then(setMe).catch(() => undefined);
  }, [clientId, locale, t]);

  async function decide(approve: boolean) {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ redirect_to: string }>("/oauth/authorize", {
        method: "POST",
        json: {
          client_id: clientId,
          redirect_uri: params.get("redirect_uri") ?? "",
          code_challenge: params.get("code_challenge") ?? "",
          code_challenge_method: params.get("code_challenge_method") ?? "S256",
          state: params.get("state") ?? "",
          scope,
          approve,
        },
      });
      window.location.assign(r.redirect_to);
    } catch (err) {
      setError((err as Error).message || t("invalid"));
      setBusy(false);
    }
  }

  if (!clientId) return <FieldError>{t("invalid")}</FieldError>;
  if (error && !client) return <FieldError>{error}</FieldError>;
  if (!client || !me) return null;
  const name = client.client_name || t("unknownClient");
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2 text-center">
        <h1 className="text-xl font-bold text-balance">{t("title", { client: name })}</h1>
        <p className="text-sm text-balance text-muted-foreground">
          {t("description", { client: name, host: client.redirect_host, user: me.display_name || me.email })}
        </p>
      </div>
      <fieldset className="grid gap-2">
        <legend className="mb-2 text-sm font-medium">{t("scope")}</legend>
        {(["write", "read"] as const).map((s) => (
          <label
            key={s}
            className={cn(
              "flex cursor-pointer items-start gap-2 rounded-lg border p-3 text-sm",
              scope === s && "border-primary bg-primary/5",
            )}
          >
            <input
              type="radio"
              name="scope"
              value={s}
              checked={scope === s}
              onChange={() => setScope(s)}
              className="mt-0.5"
            />
            {t(`scopes.${s}`)}
          </label>
        ))}
      </fieldset>
      {error && <FieldError>{error}</FieldError>}
      <div className="grid grid-cols-2 gap-2">
        <Button variant="outline" disabled={busy} onClick={() => decide(false)}>
          {t("deny")}
        </Button>
        <Button disabled={busy} onClick={() => decide(true)}>
          {t("approve")}
        </Button>
      </div>
      <p className="text-center text-xs text-muted-foreground">{t("revokeNote")}</p>
    </div>
  );
}
