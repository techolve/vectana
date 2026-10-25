"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useLocale, useTranslations } from "next-intl";

import { routing, type Locale } from "@/i18n/routing";
import { useChangeLocale } from "@/lib/use-change-locale";

import { api, SEVERITIES, type Severity } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { LabeledField, OptionSelect, PageHeader } from "@/components/common";
import { useMe } from "@/components/app-shell";

type Prefs = { email_enabled: boolean; min_severity: Severity };

export default function SettingsPage() {
  const t = useTranslations("settings");
  const me = useMe();
  const { data } = useApi<Prefs>("/auth/notifications");
  return (
    <>
      <PageHeader title={t("title")} description={me.email} />
      <div className="grid gap-6 md:grid-cols-2">
        <LanguageCard />
        {data && <PrefsCard initial={data} />}
        <PasswordCard />
      </div>
    </>
  );
}

function PrefsCard({ initial }: { initial: Prefs }) {
  const t = useTranslations();
  const [prefs, setPrefs] = useState(initial);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/auth/notifications", { method: "PUT", json: prefs });
      toast.success(t("common.saved"));
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.emailTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={save}>
          <FieldGroup>
            <Field orientation="horizontal">
              <Checkbox
                id="email-enabled"
                checked={prefs.email_enabled}
                onCheckedChange={(checked) => setPrefs({ ...prefs, email_enabled: checked === true })}
              />
              <FieldLabel htmlFor="email-enabled" className="font-normal">
                {t("settings.emailEnabled")}
              </FieldLabel>
            </Field>
            <LabeledField label={t("settings.minSeverity")} hint={t("settings.minSeverityHint")}>
              <OptionSelect
                value={prefs.min_severity}
                disabled={!prefs.email_enabled}
                onValueChange={(v) => setPrefs({ ...prefs, min_severity: v as Severity })}
                options={SEVERITIES.filter((s) => s !== "UNKNOWN").map((s) => ({
                  value: s,
                  label: t("common.atLeast", { severity: s }),
                }))}
              />
            </LabeledField>
            <div>
              <Button type="submit">{t("common.save")}</Button>
            </div>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  );
}

function PasswordCard() {
  const t = useTranslations("settings");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");

  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/auth/password", { method: "POST", json: { current_password: current, new_password: next } });
      setCurrent("");
      setNext("");
      toast.success(t("passwordChanged"));
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("passwordTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={save}>
          <FieldGroup>
            <LabeledField label={t("currentPassword")} htmlFor="current-password">
              <Input
                id="current-password"
                type="password"
                autoComplete="current-password"
                required
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
              />
            </LabeledField>
            <LabeledField label={t("newPassword")} htmlFor="new-password" hint={t("passwordHint")}>
              <Input
                id="new-password"
                type="password"
                autoComplete="new-password"
                minLength={8}
                required
                value={next}
                onChange={(e) => setNext(e.target.value)}
              />
            </LabeledField>
            <div>
              <Button type="submit">{t("change")}</Button>
            </div>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  );
}

function LanguageCard() {
  const t = useTranslations();
  const locale = useLocale();
  const changeLocale = useChangeLocale();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.languageTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <LabeledField label={t("common.language")} hint={t("settings.languageHint")}>
          <OptionSelect
            value={locale}
            onValueChange={(v) => changeLocale(v as Locale)}
            options={routing.locales.map((l) => ({ value: l, label: t(`locales.${l}`) }))}
          />
        </LabeledField>
      </CardContent>
    </Card>
  );
}
