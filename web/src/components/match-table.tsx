"use client";

import Link from "next/link";
import { toast } from "sonner";

import { api, STATUS_LABEL, type Match } from "@/lib/api";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, Select, SeverityBadge } from "@/components/common";

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
          <TableHead>重大度</TableHead>
          {showProject && <TableHead>プロジェクト</TableHead>}
          <TableHead>パッケージ</TableHead>
          <TableHead>修正版</TableHead>
          <TableHead>脆弱性</TableHead>
          <TableHead>検知日時</TableHead>
          <TableHead>状態</TableHead>
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
                <Link href={`/projects/detail/?id=${m.project_id}`} className="hover:underline">
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
                <Select value={m.status} onChange={(e) => setStatus(m, e.target.value)}>
                  {Object.entries(STATUS_LABEL).map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </Select>
              ) : (
                STATUS_LABEL[m.status]
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
