"use client";

import { useState } from "react";
import { MessageSquareIcon, PanelRightOpenIcon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { api, isOverdue, MATCH_STATUSES, type Match } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, OptionSelect, SeverityBadge, useFormatDate } from "@/components/common";
import { MatchSheet, userName } from "@/components/match-sheet";
import { UpgradeHint } from "@/components/upgrade-hint";

export function MatchTable({
  matches,
  onChanged,
  showProject = false,
  canTriage = true,
  empty,
}: {
  matches: Match[];
  onChanged: () => void;
  showProject?: boolean;
  canTriage?: boolean;
  /** Shown instead of the table when there are no rows. */
  empty?: React.ReactNode;
}) {
  const t = useTranslations();
  const formatDate = useFormatDate();
  const [openId, setOpenId] = useState<string | null>(null);
  const statusOptions = MATCH_STATUSES.map((s) => ({
    value: s,
    label: t(`labels.status.${s}`),
  }));

  async function setStatus(m: Match, status: string) {
    try {
      await api(`/vulnerabilities/${m.id}`, {
        method: "PATCH",
        json: { status },
      });
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <>
      {matches.length === 0 ? (
        <Empty>{empty}</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("matches.severity")}</TableHead>
              {showProject && <TableHead>{t("matches.project")}</TableHead>}
              <TableHead>{t("matches.package")}</TableHead>
              <TableHead>{t("matches.fixed")}</TableHead>
              <TableHead>{t("matches.vulnerability")}</TableHead>
              <TableHead>{t("matches.detected")}</TableHead>
              <TableHead>{t("triage.assignee")}</TableHead>
              <TableHead>{t("triage.dueDate")}</TableHead>
              <TableHead>{t("matches.status")}</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {matches.map((m) => (
              <TableRow key={m.id}>
                <TableCell>
                  <SeverityBadge severity={m.severity} />
                  {m.cvss_score != null && (
                    <div className="mt-0.5 text-xs text-muted-foreground">CVSS {m.cvss_score}</div>
                  )}
                </TableCell>
                {showProject && (
                  <TableCell>
                    <Link
                      href={{
                        pathname: "/projects/detail/",
                        query: { id: m.project_id },
                      }}
                      className="hover:underline"
                    >
                      {m.project_name}
                    </Link>
                  </TableCell>
                )}
                <TableCell className="font-mono text-xs">
                  <div className="text-muted-foreground">{m.ecosystem}</div>
                  {m.package_name}@{m.package_version}
                  {m.upgrade?.version && <UpgradeHint upgrade={m.upgrade} className="mt-0.5 flex" />}
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
                <TableCell className="text-xs whitespace-nowrap">
                  {m.assignee ? (
                    userName(m.assignee)
                  ) : (
                    <span className="text-muted-foreground">{t("triage.unassigned")}</span>
                  )}
                </TableCell>
                <TableCell className={cn("text-xs whitespace-nowrap", isOverdue(m) && "font-medium text-destructive")}>
                  {m.due_date ?? (m.sla_due_date ? (
                    <span title={t("triage.slaHint")}>
                      {m.sla_due_date} <span className="text-[10px] opacity-70">SLA</span>
                    </span>
                  ) : (
                    "-"
                  ))}
                  {isOverdue(m) && <div>{t("triage.overdue")}</div>}
                </TableCell>
                <TableCell>
                  {canTriage ? (
                    <OptionSelect value={m.status} onValueChange={(v) => setStatus(m, v)} options={statusOptions} />
                  ) : (
                    t(`labels.status.${m.status}`)
                  )}
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="sm" onClick={() => setOpenId(m.id)} title={t("triage.open")}>
                    {m.comment_count > 0 ? (
                      <>
                        <MessageSquareIcon /> {m.comment_count}
                      </>
                    ) : (
                      <PanelRightOpenIcon />
                    )}
                    <span className="sr-only">{t("triage.open")}</span>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {openId && <MatchSheet matchId={openId} onClose={() => setOpenId(null)} onChanged={onChanged} />}
    </>
  );
}
