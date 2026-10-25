"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";

import { useRouter } from "@/i18n/navigation";
import { api, setTokens } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

// Based on the shadcn login-02 block. Social login, password reset and sign-up
// are omitted: accounts are created by invitation only.
export function LoginForm({ className, ...props }: React.ComponentProps<"form">) {
  const t = useTranslations("login");
  const locale = useLocale();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
          {error && <FieldError>{error}</FieldError>}
          <Button type="submit" disabled={busy}>
            {t("submit")}
          </Button>
          <FieldDescription className="text-center">{t("inviteOnly")}</FieldDescription>
        </Field>
      </FieldGroup>
    </form>
  );
}
