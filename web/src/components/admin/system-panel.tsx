"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, type SystemSettings } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { LabeledField } from "@/components/common";

export function SystemPanel() {
  const { data } = useApi<SystemSettings>("/settings");
  return data ? <SystemForm initial={data} /> : null;
}

function SystemForm({ initial }: { initial: SystemSettings }) {
  const t = useTranslations();
  const [days, setDays] = useState(String(initial.eol_warning_days));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/settings", { method: "PUT", json: { eol_warning_days: Number(days) } });
      toast.success(t("common.saved"));
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>{t("system.eolTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={save}>
          <FieldGroup>
            <LabeledField label={t("system.eolWarningDays")} htmlFor="eol-days" hint={t("system.eolWarningHint")}>
              <div className="flex items-center gap-2">
                <Input
                  id="eol-days"
                  type="number"
                  min={1}
                  max={730}
                  required
                  className="w-28"
                  value={days}
                  onChange={(e) => setDays(e.target.value)}
                />
                <span className="text-sm text-muted-foreground">{t("system.days")}</span>
              </div>
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
