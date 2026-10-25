"use client";

import { useState } from "react";
import { SendIcon, Trash2Icon } from "lucide-react";
import { toast } from "sonner";

import { api, SEVERITIES, type Severity, type Webhook } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Empty, Select } from "@/components/common";

export function WebhooksPanel({ projectId }: { projectId: string }) {
  const base = `/projects/${projectId}/webhooks`;
  const { data, reload } = useApi<Webhook[]>(base);
  const [type, setType] = useState<Webhook["type"]>("discord");
  const [url, setUrl] = useState("");
  const [minSeverity, setMinSeverity] = useState<Severity>("LOW");

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
      toast.success("テスト通知を送信しました");
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  async function remove(w: Webhook) {
    if (!confirm("このWebhookを削除しますか？")) return;
    await api(`${base}/${w.id}`, { method: "DELETE" });
    reload();
  }

  return (
    <div className="grid gap-4">
      <form onSubmit={add} className="flex flex-wrap items-end gap-2 rounded-xl border p-3">
        <div className="w-full text-sm font-medium">Webhook を追加</div>
        <Select value={type} onChange={(e) => setType(e.target.value as Webhook["type"])}>
          <option value="discord">Discord</option>
          <option value="slack">Slack</option>
        </Select>
        <Input
          className="min-w-64 flex-1"
          type="url"
          required
          placeholder={type === "discord" ? "https://discord.com/api/webhooks/..." : "https://hooks.slack.com/services/..."}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <Select value={minSeverity} onChange={(e) => setMinSeverity(e.target.value as Severity)} title="この重大度以上を通知">
          {SEVERITIES.filter((s) => s !== "UNKNOWN").map((s) => (
            <option key={s} value={s}>
              {s} 以上
            </option>
          ))}
        </Select>
        <Button type="submit">追加</Button>
      </form>
      {data &&
        (data.length === 0 ? (
          <Empty>Webhook は登録されていません。チームのチャンネルに通知したい場合に追加してください。</Empty>
        ) : (
          <ul className="grid gap-2">
            {data.map((w) => (
              <li key={w.id} className="flex flex-wrap items-center gap-2 rounded-xl border p-3">
                <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium capitalize">{w.type}</span>
                <span className="min-w-0 flex-1 truncate font-mono text-xs" title={w.url}>
                  {w.url.replace(/(.{40}).+/, "$1…")}
                </span>
                <Select value={w.min_severity} onChange={(e) => update(w, { min_severity: e.target.value as Severity })}>
                  {SEVERITIES.filter((s) => s !== "UNKNOWN").map((s) => (
                    <option key={s} value={s}>
                      {s} 以上
                    </option>
                  ))}
                </Select>
                <label className="flex items-center gap-1 text-sm">
                  <input type="checkbox" checked={w.enabled} onChange={(e) => update(w, { enabled: e.target.checked })} />
                  有効
                </label>
                <Button variant="outline" size="sm" onClick={() => test(w)}>
                  <SendIcon /> テスト送信
                </Button>
                <Button variant="ghost" size="icon-sm" onClick={() => remove(w)} title="削除">
                  <Trash2Icon />
                </Button>
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}
