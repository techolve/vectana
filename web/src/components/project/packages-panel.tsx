"use client";

import { useRef, useState } from "react";
import { PlusIcon, Trash2Icon, UploadIcon } from "lucide-react";
import { toast } from "sonner";

import { api, ECOSYSTEMS, type Package } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, formatDate, Select } from "@/components/common";

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
      toast.success("登録しました。バックグラウンドでスキャンします。");
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
        toast.success(`${r.filename}: ${r.total} 件（追加 ${r.added} / 削除 ${r.removed}）`);
      } catch (err) {
        toast.error(`${file.name}: ${(err as Error).message}`);
      }
    }
    changed();
  }

  async function remove(p: Package) {
    if (!confirm(`${p.name}@${p.version} を削除しますか？`)) return;
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
            <div className="w-full text-sm font-medium">手動で登録</div>
            <Select value={ecosystem} onChange={(e) => setEcosystem(e.target.value)}>
              {ECOSYSTEMS.map((e) => (
                <option key={e}>{e}</option>
              ))}
            </Select>
            <Input className="w-40 flex-1" placeholder="パッケージ名" required value={name} onChange={(e) => setName(e.target.value)} />
            <Input className="w-28" placeholder="バージョン" required value={version} onChange={(e) => setVersion(e.target.value)} />
            <Button type="submit">
              <PlusIcon /> 追加
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
            className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border border-dashed p-3 text-center text-sm ${dragging ? "bg-muted" : ""}`}
          >
            <UploadIcon className="size-5 text-muted-foreground" />
            <span className="font-medium">lockfile をドロップして取り込み</span>
            <span className="text-xs text-muted-foreground">{LOCKFILES}</span>
            <span className="text-xs text-muted-foreground">同じファイル名で再取り込みすると差分を反映します</span>
            <input ref={fileInput} type="file" multiple className="hidden" onChange={(e) => upload(e.target.files)} />
          </div>
        </div>
      )}
      {data && data.length > 0 && (
        <Input className="max-w-xs" placeholder="絞り込み" value={q} onChange={(e) => setQ(e.target.value)} />
      )}
      {data &&
        (data.length === 0 ? (
          <Empty>パッケージが登録されていません</Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>エコシステム</TableHead>
                <TableHead>パッケージ</TableHead>
                <TableHead>バージョン</TableHead>
                <TableHead>登録元</TableHead>
                <TableHead>最終スキャン</TableHead>
                <TableHead className="text-right">未対応</TableHead>
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
                  <TableCell className={`text-right tabular-nums ${p.open_vulns ? "font-semibold text-destructive" : ""}`}>
                    {p.open_vulns}
                  </TableCell>
                  {canWrite && (
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon-sm" onClick={() => remove(p)} title="削除">
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
