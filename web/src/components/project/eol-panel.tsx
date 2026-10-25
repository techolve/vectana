"use client";

import { useEffect, useState } from "react";
import { PlusIcon, RefreshCwIcon, Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, type EolFinding, type EolProduct, type Runtime } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Empty } from "@/components/common";
import { EolTable } from "@/components/eol-table";

export function EolPanel({ projectId, canWrite, onChanged }: { projectId: string; canWrite: boolean; onChanged: () => void }) {
  const t = useTranslations();
  const { data: findings, reload: reloadFindings } = useApi<EolFinding[]>(`/eol?project_id=${projectId}`);
  const { data: runtimes, reload: reloadRuntimes } = useApi<Runtime[]>(`/projects/${projectId}/runtimes`);
  const [query, setQuery] = useState("");
  const [products, setProducts] = useState<EolProduct[]>([]);
  const [product, setProduct] = useState<EolProduct | null>(null);
  const [version, setVersion] = useState("");

  useEffect(() => {
    if (!canWrite || product) return;
    const timer = setTimeout(() => {
      api<EolProduct[]>(`/eol/products?q=${encodeURIComponent(query)}`)
        .then(setProducts)
        .catch(() => setProducts([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [query, product, canWrite]);

  const refreshSoon = () => {
    reloadRuntimes();
    setTimeout(() => {
      reloadFindings();
      onChanged();
    }, 3000);
  };

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!product) return;
    try {
      await api(`/projects/${projectId}/runtimes`, { method: "POST", json: { product: product.name, version } });
      toast.success(t("eol.runtimeAdded"));
      setProduct(null);
      setQuery("");
      setVersion("");
      refreshSoon();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  async function remove(r: Runtime) {
    if (!confirm(t("eol.confirmDeleteRuntime", { product: r.product, version: r.version }))) return;
    try {
      await api(`/projects/${projectId}/runtimes/${r.id}`, { method: "DELETE" });
      reloadRuntimes();
      reloadFindings();
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  async function recheck() {
    await api(`/projects/${projectId}/eol/refresh`, { method: "POST" });
    toast.success(t("eol.refreshStarted"));
    refreshSoon();
  }

  return (
    <div className="grid gap-4">
      <div className="grid gap-3 rounded-xl border p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-sm font-medium">{t("eol.runtimes")}</div>
            <div className="text-xs text-muted-foreground">{t("eol.runtimesHint")}</div>
          </div>
          {canWrite && (
            <Button variant="outline" size="sm" onClick={recheck}>
              <RefreshCwIcon /> {t("eol.refresh")}
            </Button>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {runtimes?.length === 0 && <span className="text-xs text-muted-foreground">{t("eol.noRuntimes")}</span>}
          {runtimes?.map((r) => (
            <Badge key={r.id} variant="secondary" className="gap-1 pr-1">
              {r.product} {r.version}
              {canWrite && (
                <button className="rounded p-0.5 hover:bg-background" title={t("common.delete")} onClick={() => remove(r)}>
                  <Trash2Icon className="size-3" />
                </button>
              )}
            </Badge>
          ))}
        </div>
        {canWrite && (
          <form onSubmit={add} className="grid gap-2">
            <div className="flex flex-wrap items-center gap-2">
              {product ? (
                <Badge className="h-8 gap-1 px-2">
                  {product.label}
                  <button type="button" className="ml-1 opacity-80 hover:opacity-100" onClick={() => setProduct(null)}>
                    ×
                  </button>
                </Badge>
              ) : (
                <Input className="w-56" placeholder={t("eol.searchProduct")} value={query} onChange={(e) => setQuery(e.target.value)} />
              )}
              <Input
                className="w-40"
                placeholder={t("eol.versionPlaceholder")}
                required
                value={version}
                onChange={(e) => setVersion(e.target.value)}
              />
              <Button type="submit" disabled={!product}>
                <PlusIcon /> {t("common.add")}
              </Button>
            </div>
            {!product && query && (
              <div className="flex flex-wrap gap-1">
                {products.slice(0, 12).map((p) => (
                  <Button key={p.name} type="button" variant="outline" size="xs" onClick={() => setProduct(p)}>
                    {p.label}
                  </Button>
                ))}
              </div>
            )}
          </form>
        )}
      </div>
      {findings && (findings.length === 0 ? <Empty>{t("eol.empty")}</Empty> : <EolTable findings={findings} />)}
    </div>
  );
}
