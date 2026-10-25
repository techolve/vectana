"use client";

import { useState } from "react";
import { SendIcon, Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, SEVERITIES, type Severity, type Webhook } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Empty, OptionSelect } from "@/components/common";

const TYPES = [
  { value: "discord", label: "Discord" },
  { value: "slack", label: "Slack" },
];

export function WebhooksPanel({ projectId }: { projectId: string }) {
  const t = useTranslations();
  const base = `/projects/${projectId}/webhooks`;
  const { data, reload } = useApi<Webhook[]>(base);
  const [type, setType] = useState<string>("discord");
  const [url, setUrl] = useState("");
  const [minSeverity, setMinSeverity] = useState<string>("LOW");
  const severityOptions = SEVERITIES.filter((s) => s !== "UNKNOWN").map((s) => ({
    value: s,
    label: t("common.atLeast", { severity: s }),
  }));

  async function add(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(base, { method: "POST", json: { type, url, min_severity: minSeverity, enabled: true } });
      setUrl("");
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  async function update(w: Webhook, patch: Partial<Webhook>) {
    try {
      await api(`${base}/${w.id}`, { method: "PUT", json: { ...w, ...patch } });
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  async function test(w: Webhook) {
    try {
      await api(`${base}/${w.id}/test`, { method: "POST" });
      toast.success(t("webhooks.testSent"));
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  async function remove(w: Webhook) {
    if (!confirm(t("webhooks.confirmDelete"))) return;
    await api(`${base}/${w.id}`, { method: "DELETE" });
    reload();
  }

  return (
    <div className="grid gap-4">
      <form onSubmit={add} className="flex flex-wrap items-end gap-2 rounded-xl border p-3">
        <div className="w-full text-sm font-medium">{t("webhooks.add")}</div>
        <OptionSelect value={type} onValueChange={setType} options={TYPES} />
        <Input
          className="min-w-64 flex-1"
          type="url"
          required
          placeholder={type === "discord" ? "https://discord.com/api/webhooks/..." : "https://hooks.slack.com/services/..."}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <OptionSelect value={minSeverity} onValueChange={setMinSeverity} options={severityOptions} title={t("webhooks.minSeverity")} />
        <Button type="submit">{t("common.add")}</Button>
      </form>
      {data &&
        (data.length === 0 ? (
          <Empty>{t("webhooks.empty")}</Empty>
        ) : (
          <ul className="grid gap-2">
            {data.map((w) => (
              <li key={w.id} className="flex flex-wrap items-center gap-2 rounded-xl border p-3">
                <Badge variant="secondary" className="capitalize">
                  {w.type}
                </Badge>
                <span className="min-w-0 flex-1 truncate font-mono text-xs" title={w.url}>
                  {w.url.replace(/(.{40}).+/, "$1…")}
                </span>
                <OptionSelect
                  value={w.min_severity}
                  onValueChange={(v) => update(w, { min_severity: v as Severity })}
                  options={severityOptions}
                />
                <Label className="flex items-center gap-2 text-sm font-normal">
                  <Checkbox checked={w.enabled} onCheckedChange={(checked) => update(w, { enabled: checked === true })} />
                  {t("common.enabled")}
                </Label>
                <Button variant="outline" size="sm" onClick={() => test(w)}>
                  <SendIcon /> {t("common.testSend")}
                </Button>
                <Button variant="ghost" size="icon-sm" onClick={() => remove(w)} title={t("common.delete")}>
                  <Trash2Icon />
                </Button>
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}
