"use client";

import { useLocale, useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import type { EolFinding, EolStatus } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export const EOL_STYLE: Record<EolStatus, string> = {
  eol: "bg-red-600 text-white",
  approaching: "bg-orange-500 text-white",
  supported: "bg-emerald-600 text-white",
  unknown: "bg-muted text-muted-foreground",
};

export function EolBadge({ status }: { status: EolStatus }) {
  const t = useTranslations("eol");
  return (
    <span className={cn("inline-flex justify-center rounded px-1.5 py-0.5 text-[11px] font-semibold", EOL_STYLE[status])}>
      {t(`statusLabel.${status}`)}
    </span>
  );
}

const DAY = 24 * 60 * 60 * 1000;

export function EolTable({ findings, showProject = false }: { findings: EolFinding[]; showProject?: boolean }) {
  const t = useTranslations("eol");
  const locale = useLocale();
  const today = new Date(new Date().toDateString()).getTime();

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("status")}</TableHead>
          {showProject && <TableHead>{t("source")}</TableHead>}
          <TableHead>{t("product")}</TableHead>
          <TableHead>{t("version")}</TableHead>
          <TableHead>{t("eolDate")}</TableHead>
          <TableHead>{t("latest")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {findings.map((f) => {
          const days = f.eol_date ? Math.round((new Date(f.eol_date).getTime() - today) / DAY) : null;
          return (
            <TableRow key={f.id}>
              <TableCell>
                <EolBadge status={f.status} />
              </TableCell>
              {showProject && (
                <TableCell>
                  <Link href={{ pathname: "/projects/detail/", query: { id: f.project_id } }} className="hover:underline">
                    {f.project_name}
                  </Link>
                </TableCell>
              )}
              <TableCell>
                <a href={`https://endoflife.date/${f.product}`} target="_blank" rel="noreferrer" className="font-medium hover:underline">
                  {f.product_label}
                </a>
                <Badge variant="outline" className="ml-2">
                  {f.source === "runtime" ? t("sourceRuntime") : t("sourcePackage")}
                </Badge>
              </TableCell>
              <TableCell className="font-mono text-xs">
                {f.version}
                {f.cycle && f.cycle !== f.version && <span className="ml-1 text-muted-foreground">({f.cycle})</span>}
              </TableCell>
              <TableCell className="text-xs">
                {f.eol_date ? new Date(f.eol_date).toLocaleDateString(locale) : "-"}
                {days !== null && (f.status === "eol" || f.status === "approaching") && (
                  <div className={cn("text-muted-foreground", f.status === "eol" && "text-destructive")}>
                    {days >= 0 ? t("daysLeft", { days }) : t("daysAgo", { days: -days })}
                  </div>
                )}
              </TableCell>
              <TableCell className="font-mono text-xs">{f.latest ?? "-"}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
