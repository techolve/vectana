"use client";

import { useRef, useState } from "react";
import { PlusIcon, Trash2Icon, UploadIcon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, ECOSYSTEMS, type Package } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, OptionSelect, useFormatDate } from "@/components/common";

type ImportResult = { filename: string; ecosystem: string; added: number; removed: number; total: number };

const LOCKFILES = "package-lock.json / pnpm-lock.yaml / uv.lock / poetry.lock / requirements*.txt / pubspec.lock";

export function PackagesPanel({
  projectId,
  canWrite,
  onChanged,
}: {
  projectId: string;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const t = useTranslations("packages");
  const formatDate = useFormatDate();
  const { data, reload } = useApi<Package[]>(`/projects/${projectId}/packages`);
  const [ecosystem, setEcosystem] = useState("npm");
  const [name, setName] = useState("");
  const [version, setVersion] = useState("");
  const [q, setQ] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const changed = () => {
    reload();
    onChanged();
  };

  async function add(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`/projects/${projectId}/packages`, { method: "POST", json: { ecosystem, name, version } });
      setName("");
      setVersion("");
      toast.success(t("added"));
      changed();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  async function upload(files: FileList | null) {
    for (const file of Array.from(files ?? [])) {
      const form = new FormData();
      form.append("file", file);
      try {
        const r = await api<ImportResult>(`/projects/${projectId}/packages/import`, { method: "POST", body: form });
        toast.success(t("imported", { file: r.filename, total: r.total, added: r.added, removed: r.removed }));
      } catch (err) {
        toast.error(`${file.name}: ${(err as Error).message}`);
      }
    }
    changed();
  }

  async function remove(p: Package) {
    if (!confirm(t("confirmDelete", { name: p.name, version: p.version }))) return;
    try {
      await api(`/projects/${projectId}/packages/${p.id}`, { method: "DELETE" });
      changed();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  const needle = q.trim().toLowerCase();
  const rows = (data ?? []).filter((p) => !needle || `${p.ecosystem} ${p.name} ${p.version}`.toLowerCase().includes(needle));

  return (
    <div className="grid gap-4">
      {canWrite && (
        <div className="grid gap-3 md:grid-cols-2">
          <form onSubmit={add} className="flex flex-wrap items-end gap-2 rounded-xl border p-3">
            <div className="w-full text-sm font-medium">{t("manual")}</div>
            <OptionSelect value={ecosystem} onValueChange={setEcosystem} options={ECOSYSTEMS.map((e) => ({ value: e, label: e }))} />
            <Input className="w-40 flex-1" placeholder={t("namePlaceholder")} required value={name} onChange={(e) => setName(e.target.value)} />
            <Input className="w-28" placeholder={t("versionPlaceholder")} required value={version} onChange={(e) => setVersion(e.target.value)} />
            <Button type="submit">
              <PlusIcon />
            </Button>
          </form>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              upload(e.dataTransfer.files);
            }}
            onClick={() => fileInput.current?.click()}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border border-dashed p-3 text-center text-sm",
              dragging && "bg-muted",
            )}
          >
            <UploadIcon className="size-5 text-muted-foreground" />
            <span className="font-medium">{t("drop")}</span>
            <span className="text-xs text-muted-foreground">{LOCKFILES}</span>
            <span className="text-xs text-muted-foreground">{t("reimportHint")}</span>
            <input ref={fileInput} type="file" multiple className="hidden" onChange={(e) => upload(e.target.files)} />
          </div>
        </div>
      )}
      {data && data.length > 0 && (
        <Input className="max-w-xs" placeholder={t("namePlaceholder")} value={q} onChange={(e) => setQ(e.target.value)} />
      )}
      {data &&
        (data.length === 0 ? (
          <Empty>{t("empty")}</Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("ecosystem")}</TableHead>
                <TableHead>{t("package")}</TableHead>
                <TableHead>{t("version")}</TableHead>
                <TableHead>{t("source")}</TableHead>
                <TableHead>{t("lastScanned")}</TableHead>
                <TableHead className="text-right">{t("open")}</TableHead>
                {canWrite && <TableHead />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="text-xs">{p.ecosystem}</TableCell>
                  <TableCell className="font-mono text-xs">{p.name}</TableCell>
                  <TableCell className="font-mono text-xs">{p.version}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{p.source.replace("lockfile:", "")}</TableCell>
                  <TableCell className="text-xs">{formatDate(p.last_scanned_at)}</TableCell>
                  <TableCell className={cn("text-right tabular-nums", p.open_vulns && "font-semibold text-destructive")}>
                    {p.open_vulns}
                  </TableCell>
                  {canWrite && (
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon-sm" onClick={() => remove(p)} title={t("confirmDelete", { name: p.name, version: p.version })}>
                        <Trash2Icon />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ))}
    </div>
  );
}
