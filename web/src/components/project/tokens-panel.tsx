"use client";

import { useState } from "react";
import { CopyIcon, KeyRoundIcon, Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, type ApiToken } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, OptionSelect, useFormatDate } from "@/components/common";

const EXPIRY_DAYS = ["30", "90", "365", "never"] as const;

function ciExample(projectId: string): string {
  const origin = typeof window === "undefined" ? "https://vectana.example.com" : window.location.origin;
  return `# .github/workflows/sbom.yml
name: SBOM
on:
  push:
    branches: [main]
jobs:
  sbom:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: anchore/sbom-action@v0
        with:
          format: cyclonedx-json
          output-file: bom.json
          upload-artifact: false
      - name: Upload to Vectana
        run: |
          curl -fsS -X POST \\
            -H "Authorization: Bearer \${{ secrets.VECTANA_TOKEN }}" \\
            -F "file=@bom.json" \\
            -F "source=\${{ github.event.repository.name }}" \\
            ${origin}/api/projects/${projectId}/packages/import`;
}

function CopyBlock({ text, label }: { text: string; label: string }) {
  const t = useTranslations("tokens");
  async function copy() {
    await navigator.clipboard.writeText(text);
    toast.success(t("copied"));
  }
  return (
    <div className="grid gap-1">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">{label}</span>
        <Button variant="outline" size="sm" onClick={copy}>
          <CopyIcon /> {t("copy")}
        </Button>
      </div>
      <pre className="overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs whitespace-pre">{text}</pre>
    </div>
  );
}

export function TokensPanel({ projectId }: { projectId: string }) {
  const t = useTranslations("tokens");
  const formatDate = useFormatDate();
  const base = `/projects/${projectId}/tokens`;
  const { data, reload } = useApi<ApiToken[]>(base);
  const [name, setName] = useState("");
  const [expiry, setExpiry] = useState<string>("365");
  const [issued, setIssued] = useState<string | null>(null);
  const expiryOptions = EXPIRY_DAYS.map((d) => ({ value: d, label: t(`expiry.${d}`) }));

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      const r = await api<ApiToken & { token: string }>(base, {
        method: "POST",
        json: { name, expires_in_days: expiry === "never" ? null : Number(expiry) },
      });
      setIssued(r.token);
      setName("");
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  async function revoke(token: ApiToken) {
    if (!confirm(t("confirmRevoke", { name: token.name }))) return;
    try {
      await api(`${base}/${token.id}`, { method: "DELETE" });
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted-foreground">{t("description")}</p>
      <form onSubmit={create} className="flex flex-wrap items-end gap-2 rounded-xl border p-3">
        <div className="w-full text-sm font-medium">{t("issue")}</div>
        <Input
          className="min-w-64 flex-1"
          required
          maxLength={100}
          placeholder={t("namePlaceholder")}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <OptionSelect value={expiry} onValueChange={setExpiry} options={expiryOptions} title={t("expiresAt")} />
        <Button type="submit">
          <KeyRoundIcon /> {t("issueButton")}
        </Button>
      </form>
      {issued && (
        <div className="grid gap-3 rounded-xl border border-amber-500/50 bg-amber-500/5 p-3">
          <p className="text-sm font-medium">{t("issuedOnce")}</p>
          <CopyBlock text={issued} label={t("token")} />
          <Button variant="ghost" size="sm" className="justify-self-end" onClick={() => setIssued(null)}>
            {t("done")}
          </Button>
        </div>
      )}
      {data &&
        (data.length === 0 ? (
          <Empty>{t("empty")}</Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("name")}</TableHead>
                <TableHead>{t("token")}</TableHead>
                <TableHead>{t("createdBy")}</TableHead>
                <TableHead>{t("createdAt")}</TableHead>
                <TableHead>{t("expiresAt")}</TableHead>
                <TableHead>{t("lastUsed")}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((tok) => {
                const expired = tok.expires_at !== null && new Date(tok.expires_at) <= new Date();
                return (
                  <TableRow key={tok.id}>
                    <TableCell className="font-medium">{tok.name}</TableCell>
                    <TableCell className="font-mono text-xs">{tok.prefix}…</TableCell>
                    <TableCell className="text-xs">{tok.created_by_email ?? "-"}</TableCell>
                    <TableCell className="text-xs">{formatDate(tok.created_at)}</TableCell>
                    <TableCell className={expired ? "text-xs text-destructive" : "text-xs"}>
                      {tok.expires_at ? formatDate(tok.expires_at) : t("expiry.never")}
                      {expired && `（${t("expired")}）`}
                    </TableCell>
                    <TableCell className="text-xs">{formatDate(tok.last_used_at)}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon-sm" onClick={() => revoke(tok)} title={t("revoke")}>
                        <Trash2Icon />
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        ))}
      <CopyBlock text={ciExample(projectId)} label={t("example")} />
      <p className="text-xs text-muted-foreground">{t("exampleNote", { secret: "VECTANA_TOKEN" })}</p>
    </div>
  );
}
