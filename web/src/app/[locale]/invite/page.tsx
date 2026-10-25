"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";

import { useRouter } from "@/i18n/navigation";
import { api, ApiError, setTokens } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { AuthLayout } from "@/components/auth-layout";

type Preview = { email: string; display_name: string | null; company_name: string };

function InviteForm() {
  const t = useTranslations("invite");
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api<Preview>(`/auth/invitations/${encodeURIComponent(token)}`, { auth: false })
      .then((p) => {
        setPreview(p);
        setName(p.display_name ?? "");
      })
      .catch((e: ApiError) => setLoadError(e.status === 410 ? t("expired") : t("notFound")));
  }, [token, t]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) return setError(t("mismatch"));
    try {
      const tokens = await api<{ access_token: string; refresh_token: string }>("/auth/invitations/accept", {
        method: "POST",
        json: { token, password, display_name: name || null },
        auth: false,
      });
      setTokens(tokens.access_token, tokens.refresh_token);
      router.replace("/");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (!token || loadError) return <FieldError>{loadError ?? t("invalidLink")}</FieldError>;
  if (!preview) return <p className="text-center text-sm text-muted-foreground">{t("checking")}</p>;

  return (
    <form onSubmit={submit}>
      <FieldGroup>
        <FieldDescription className="text-center">
          {t("description", { company: preview.company_name, email: preview.email })}
        </FieldDescription>
        <Field>
          <FieldLabel htmlFor="name">{t("displayName")}</FieldLabel>
          <Input id="name" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field>
          <FieldLabel htmlFor="password">{t("password")}</FieldLabel>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <FieldDescription>{t("passwordHint")}</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="confirm">{t("confirm")}</FieldLabel>
          <Input
            id="confirm"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </Field>
        <Field>
          {error && <FieldError>{error}</FieldError>}
          <Button type="submit">{t("submit")}</Button>
        </Field>
      </FieldGroup>
    </form>
  );
}

export default function InvitePage() {
  const t = useTranslations("invite");
  return (
    <AuthLayout>
      <div className="flex flex-col gap-6">
        <h1 className="text-center text-2xl font-bold">{t("title")}</h1>
        <Suspense>
          <InviteForm />
        </Suspense>
      </div>
    </AuthLayout>
  );
}
