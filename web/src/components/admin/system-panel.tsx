"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, type Severity, type SystemSettings } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LabeledField, OptionSelect, SeverityBadge } from "@/components/common";

const SLA_FIELDS: [Severity, keyof SystemSettings][] = [
  ["CRITICAL", "sla_critical_days"],
  ["HIGH", "sla_high_days"],
  ["MEDIUM", "sla_medium_days"],
  ["LOW", "sla_low_days"],
  ["UNKNOWN", "sla_unknown_days"],
];

export function SystemPanel() {
  const { data } = useApi<SystemSettings>("/settings");
  return data ? <SystemForm initial={data} /> : null;
}

function SystemForm({ initial }: { initial: SystemSettings }) {
  const t = useTranslations();
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      ["eol_warning_days", ...SLA_FIELDS.map(([, key]) => key)].map((key) => [
        key,
        String(initial[key as keyof SystemSettings]),
      ]),
    ),
  );
  const [reportEnabled, setReportEnabled] = useState(initial.report_enabled);
  const [weekday, setWeekday] = useState(String(initial.report_weekday));

  async function save(json: Partial<SystemSettings>) {
    try {
      await api("/settings", { method: "PUT", json });
      toast.success(t("common.saved"));
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  function daysInput(key: string, max: number) {
    return (
      <div className="flex items-center gap-2">
        <Input
          id={key}
          type="number"
          min={1}
          max={max}
          required
          className="w-28"
          value={values[key]}
          onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
        />
        <span className="text-sm text-muted-foreground">{t("system.days")}</span>
      </div>
    );
  }

  return (
    <div className="grid max-w-xl gap-4">
      <Card>
        <CardHeader>
          <CardTitle>{t("system.eolTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              save({ eol_warning_days: Number(values.eol_warning_days) });
            }}
          >
            <FieldGroup>
              <LabeledField label={t("system.eolWarningDays")} htmlFor="eol_warning_days" hint={t("system.eolWarningHint")}>
                {daysInput("eol_warning_days", 730)}
              </LabeledField>
              <div>
                <Button type="submit">{t("common.save")}</Button>
              </div>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("system.slaTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              save(Object.fromEntries(SLA_FIELDS.map(([, key]) => [key, Number(values[key])])));
            }}
          >
            <FieldGroup>
              <p className="text-sm text-muted-foreground">{t("system.slaHint")}</p>
              <div className="grid gap-3">
                {SLA_FIELDS.map(([severity, key]) => (
                  <div key={key} className="flex items-center gap-3">
                    <Label htmlFor={key} className="w-24">
                      <SeverityBadge severity={severity} />
                    </Label>
                    {daysInput(key, 3650)}
                  </div>
                ))}
              </div>
              <div>
                <Button type="submit">{t("common.save")}</Button>
              </div>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("system.reportTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              save({ report_enabled: reportEnabled, report_weekday: Number(weekday) });
            }}
          >
            <FieldGroup>
              <div className="flex items-start gap-2">
                <Checkbox id="report-enabled" checked={reportEnabled} onCheckedChange={(v) => setReportEnabled(!!v)} />
                <Label htmlFor="report-enabled" className="leading-snug font-normal">
                  {t("system.reportEnabled")}
                </Label>
              </div>
              <LabeledField label={t("system.reportWeekday")} hint={t("system.reportHint")}>
                <OptionSelect
                  value={weekday}
                  onValueChange={setWeekday}
                  disabled={!reportEnabled}
                  className="w-40"
                  options={(["0", "1", "2", "3", "4", "5", "6"] as const).map((d) => ({ value: d, label: t(`system.weekdays.${d}`) }))}
                />
              </LabeledField>
              <div>
                <Button type="submit">{t("common.save")}</Button>
              </div>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
