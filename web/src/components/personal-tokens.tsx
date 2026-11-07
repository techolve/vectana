"use client";

import { useState } from "react";
import { KeyRoundIcon, Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, type PersonalToken, type TokenScope } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, OptionSelect, useFormatDate } from "@/components/common";
import { CopyBlock } from "@/components/project/tokens-panel";

const EXPIRY_DAYS = ["30", "90", "365", "never"] as const;
const SCOPES: TokenScope[] = ["read", "write"];

function origin(): string {
  return typeof window === "undefined" ? "https://vectana.example.com" : window.location.origin;
}

function mcpConfig(token: string): string {
  return JSON.stringify(
    {
      mcpServers: {
        vectana: {
          command: "npx",
          args: ["-y", "@techolve/vectana-mcp"],
          env: { VECTANA_URL: origin(), VECTANA_TOKEN: token },
        },
      },
    },
    null,
    2,
  );
}

function claudeCodeCommand(token: string): string {
  return `claude mcp add vectana -e VECTANA_URL=${origin()} -e VECTANA_TOKEN=${token} -- npx -y @techolve/vectana-mcp`;
}

/** Personal tokens: act as the user from AI clients (the Vectana MCP server) and scripts. */
export function PersonalTokensCard() {
  const t = useTranslations("personalTokens");
  const tk = useTranslations("tokens");
  const formatDate = useFormatDate();
  const base = "/auth/tokens";
  const { data, reload } = useApi<PersonalToken[]>(base);
  const [name, setName] = useState("");
  const [scope, setScope] = useState<TokenScope>("read");
  const [expiry, setExpiry] = useState<string>("90");
  const [issued, setIssued] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      const r = await api<PersonalToken & { token: string }>(base, {
        method: "POST",
        json: { name, scope, expires_in_days: expiry === "never" ? null : Number(expiry) },
      });
      setIssued(r.token);
      setName("");
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  async function revoke(token: PersonalToken) {
    if (!confirm(t("confirmRevoke", { name: token.name }))) return;
    try {
      await api(`${base}/${token.id}`, { method: "DELETE" });
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  const shown = issued ?? "vcu_...";
  return (
    <Card className="md:col-span-2">
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
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
          <OptionSelect
            value={scope}
            onValueChange={(v) => setScope(v as TokenScope)}
            options={SCOPES.map((s) => ({ value: s, label: t(`scopes.${s}`) }))}
            title={t("scope")}
          />
          <OptionSelect
            value={expiry}
            onValueChange={setExpiry}
            options={EXPIRY_DAYS.map((d) => ({ value: d, label: tk(`expiry.${d}`) }))}
            title={tk("expiresAt")}
          />
          <Button type="submit">
            <KeyRoundIcon /> {tk("issueButton")}
          </Button>
        </form>
        {issued && (
          <div className="grid gap-3 rounded-xl border border-amber-500/50 bg-amber-500/5 p-3">
            <p className="text-sm font-medium">{t("issuedOnce")}</p>
            <CopyBlock text={issued} label={tk("token")} />
            <Button variant="ghost" size="sm" className="justify-self-end" onClick={() => setIssued(null)}>
              {tk("done")}
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
                  <TableHead>{tk("name")}</TableHead>
                  <TableHead>{tk("token")}</TableHead>
                  <TableHead>{t("scope")}</TableHead>
                  <TableHead>{tk("createdAt")}</TableHead>
                  <TableHead>{tk("expiresAt")}</TableHead>
                  <TableHead>{tk("lastUsed")}</TableHead>
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
                      <TableCell>
                        <Badge variant={tok.scope === "write" ? "default" : "secondary"}>
                          {t(`scopes.${tok.scope}`)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">{formatDate(tok.created_at)}</TableCell>
                      <TableCell className={expired ? "text-xs text-destructive" : "text-xs"}>
                        {tok.expires_at ? formatDate(tok.expires_at) : tk("expiry.never")}
                        {expired && `（${tk("expired")}）`}
                      </TableCell>
                      <TableCell className="text-xs">{formatDate(tok.last_used_at)}</TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="icon-sm" onClick={() => revoke(tok)} title={tk("revoke")}>
                          <Trash2Icon />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          ))}
        <CopyBlock text={mcpConfig(shown)} label={t("mcpExample")} />
        <p className="text-xs break-all text-muted-foreground">
          {t("mcpNote", { command: claudeCodeCommand(shown) })}
        </p>
      </CardContent>
    </Card>
  );
}
