"use client";

import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { api, type Match } from "@/lib/api";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { OptionSelect, SeverityBadge, useFormatDate } from "@/components/common";

const STATUSES = ["open", "ack", "ignored"] as const;

export function MatchTable({
  matches,
  onChanged,
  showProject = false,
  canTriage = true,
}: {
  matches: Match[];
  onChanged: () => void;
  showProject?: boolean;
  canTriage?: boolean;
}) {
  const t = useTranslations();
  const formatDate = useFormatDate();
  const statusOptions = STATUSES.map((s) => ({ value: s, label: t(`labels.status.${s}`) }));

  async function setStatus(m: Match, status: string) {
    try {
      await api(`/vulnerabilities/${m.id}`, { method: "PATCH", json: { status } });
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("matches.severity")}</TableHead>
          {showProject && <TableHead>{t("matches.project")}</TableHead>}
          <TableHead>{t("matches.package")}</TableHead>
          <TableHead>{t("matches.fixed")}</TableHead>
          <TableHead>{t("matches.vulnerability")}</TableHead>
          <TableHead>{t("matches.detected")}</TableHead>
          <TableHead>{t("matches.status")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {matches.map((m) => (
          <TableRow key={m.id}>
            <TableCell>
              <SeverityBadge severity={m.severity} />
              {m.cvss_score != null && <div className="mt-0.5 text-xs text-muted-foreground">CVSS {m.cvss_score}</div>}
            </TableCell>
            {showProject && (
              <TableCell>
                <Link href={{ pathname: "/projects/detail/", query: { id: m.project_id } }} className="hover:underline">
                  {m.project_name}
                </Link>
              </TableCell>
            )}
            <TableCell className="font-mono text-xs">
              <div className="text-muted-foreground">{m.ecosystem}</div>
              {m.package_name}@{m.package_version}
            </TableCell>
            <TableCell className="font-mono text-xs">{m.fixed_version ?? "-"}</TableCell>
            <TableCell className="max-w-md whitespace-normal">
              <a
                href={`https://osv.dev/vulnerability/${m.vuln_id}`}
                target="_blank"
                rel="noreferrer"
                className="font-mono text-xs font-medium hover:underline"
              >
                {m.vuln_id}
              </a>
              {m.aliases.length > 0 && (
                <span className="ml-1 font-mono text-xs text-muted-foreground">({m.aliases.join(", ")})</span>
              )}
              {m.summary && <div className="text-xs text-muted-foreground">{m.summary}</div>}
            </TableCell>
            <TableCell className="text-xs">{formatDate(m.first_seen_at)}</TableCell>
            <TableCell>
              {canTriage ? (
                <OptionSelect value={m.status} onValueChange={(v) => setStatus(m, v)} options={statusOptions} />
              ) : (
                t(`labels.status.${m.status}`)
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
