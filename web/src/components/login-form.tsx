"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";

import { useRouter } from "@/i18n/navigation";
import { api, setTokens } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldSeparator,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";

type SsoConfig = { enabled: boolean; provider_name: string };

const SSO_ERRORS = ["not_registered", "expired", "denied", "provider", "no_email"] as const;

// Based on the shadcn login-02 block. Password reset and sign-up are omitted:
// accounts are created by invitation only. SSO (OIDC) appears when the server
// has it configured, and signs in existing users only.
export function LoginForm({ className, ...props }: React.ComponentProps<"form">) {
  const t = useTranslations("login");
  const locale = useLocale();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sso, setSso] = useState<SsoConfig | null>(null);

  // The SSO callback sends failures back here as ?sso_error=<reason>.
  const reason = useSearchParams().get("sso_error");
  const ssoError = reason
    ? t(`ssoErrors.${SSO_ERRORS.find((r) => r === reason) ?? "provider"}`)
    : null;

  useEffect(() => {
    api<SsoConfig>("/auth/oidc/config", { auth: false })
      .then(setSso)
      .catch(() => setSso(null));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const tokens = await api<{ access_token: string; refresh_token: string }>("/auth/login", {
        method: "POST",
        json: { email, password },
        auth: false,
      });
      setTokens(tokens.access_token, tokens.refresh_token);
      // Emails follow the language the user works in.
      await api("/auth/locale", { method: "PUT", json: { locale } }).catch(() => undefined);
      router.replace("/");
    } catch (err) {
      setError((err as Error).message || t("invalid"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className={cn("flex flex-col gap-6", className)} {...props}>
      <FieldGroup>
        <div className="flex flex-col items-center gap-1 text-center">
          <h1 className="text-2xl font-bold">{t("title")}</h1>
          <p className="text-sm text-balance text-muted-foreground">{t("description")}</p>
        </div>
        <Field>
          <FieldLabel htmlFor="email">{t("email")}</FieldLabel>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="m@example.com"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="password">{t("password")}</FieldLabel>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <Field>
          {(error ?? ssoError) && <FieldError>{error ?? ssoError}</FieldError>}
          <Button type="submit" disabled={busy}>
            {t("submit")}
          </Button>
        </Field>
        {sso?.enabled && (
          <>
            <FieldSeparator>{t("or")}</FieldSeparator>
            <Field>
              {/* A plain link: the browser leaves the app for the identity provider. */}
              <a
                href={`/api/auth/oidc/login?locale=${locale}`}
                className={buttonVariants({ variant: "outline" })}
              >
                {t("sso", { provider: sso.provider_name })}
              </a>
            </Field>
          </>
        )}
        <Field>
          <FieldDescription className="text-center">{t("inviteOnly")}</FieldDescription>
        </Field>
      </FieldGroup>
    </form>
  );
}
