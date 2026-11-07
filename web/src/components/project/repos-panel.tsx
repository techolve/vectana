"use client";

import { useState } from "react";
import { DownloadIcon, ExternalLinkIcon, GitBranchIcon, KeyRoundIcon, ListTodoIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, type RepoImport, type RepoLink, type RepoProvider } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Empty, ErrorText, LabeledField, OptionSelect, useFormatDate } from "@/components/common";
import { CopyBlock } from "@/components/project/tokens-panel";

const PROVIDERS: { value: RepoProvider; label: string }[] = [
  { value: "github", label: "GitHub" },
  { value: "gitlab", label: "GitLab" },
];

function splitPaths(text: string): string[] {
  return text
    .split(/[\n,]/)
    .map((p) => p.trim())
    .filter(Boolean);
}

export function ReposPanel({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const t = useTranslations("repos");
  const { data, reload } = useApi<RepoLink[]>(`/projects/${projectId}/repo-links`);
  const [adding, setAdding] = useState(false);

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="max-w-3xl text-sm text-muted-foreground">{t("description")}</p>
        {canManage && (
          <Button onClick={() => setAdding(true)}>
            <PlusIcon /> {t("add")}
          </Button>
        )}
      </div>
      {data &&
        (data.length === 0 ? (
          <Empty>{t("empty")}</Empty>
        ) : (
          data.map((link) => <RepoCard key={link.id} link={link} canManage={canManage} onChanged={reload} />)
        ))}
      {adding && (
        <AddRepoDialog
          projectId={projectId}
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            reload();
            // The first import and issue pull run in the background.
            setTimeout(reload, 4000);
          }}
        />
      )}
    </div>
  );
}

function AddRepoDialog({ projectId, onClose, onSaved }: { projectId: string; onClose: () => void; onSaved: () => void }) {
  const t = useTranslations("repos");
  const tc = useTranslations("common");
  const [provider, setProvider] = useState<RepoProvider>("github");
  const [selfHosted, setSelfHosted] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [repo, setRepo] = useState("");
  const [token, setToken] = useState("");
  const [syncIssues, setSyncIssues] = useState(true);
  const [securityIssues, setSecurityIssues] = useState(true);
  const [paths, setPaths] = useState("");
  const [registerWebhook, setRegisterWebhook] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api(`/projects/${projectId}/repo-links`, {
        method: "POST",
        json: {
          provider,
          base_url: selfHosted && baseUrl ? baseUrl : null,
          repo: repo.trim(),
          token,
          sync_issues: syncIssues,
          security_issues: securityIssues,
          import_paths: splitPaths(paths),
          register_webhook: registerWebhook,
        },
      });
      toast.success(t("linked"));
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("add")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={save}>
          <FieldGroup>
            <div className="grid gap-4 sm:grid-cols-[10rem_1fr]">
              <LabeledField label={t("provider")}>
                <OptionSelect value={provider} onValueChange={(v) => setProvider(v as RepoProvider)} options={PROVIDERS} />
              </LabeledField>
              <LabeledField label={t("repo")} htmlFor="repo-name" hint={t(provider === "github" ? "repoHintGithub" : "repoHintGitlab")}>
                <Input
                  id="repo-name"
                  required
                  pattern="[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)+"
                  placeholder={provider === "github" ? "acme/portal" : "group/subgroup/portal"}
                  value={repo}
                  onChange={(e) => setRepo(e.target.value)}
                />
              </LabeledField>
            </div>
            <Label className="flex items-center gap-2 font-normal">
              <Checkbox checked={selfHosted} onCheckedChange={(v) => setSelfHosted(!!v)} />
              {t(provider === "github" ? "enterprise" : "selfHosted")}
            </Label>
            {selfHosted && (
              <LabeledField label={t("baseUrl")} htmlFor="repo-base" hint={t(provider === "github" ? "baseUrlHintGithub" : "baseUrlHintGitlab")}>
                <Input
                  id="repo-base"
                  type="url"
                  required
                  placeholder={provider === "github" ? "https://github.example.com/api/v3" : "https://gitlab.example.com"}
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                />
              </LabeledField>
            )}
            <LabeledField label={t("token")} htmlFor="repo-token" hint={t(provider === "github" ? "tokenHintGithub" : "tokenHintGitlab")}>
              <Input id="repo-token" type="password" required autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} />
            </LabeledField>
            <div className="grid gap-2">
              <Label className="flex items-center gap-2 font-normal">
                <Checkbox checked={syncIssues} onCheckedChange={(v) => setSyncIssues(!!v)} />
                {t("syncIssues")}
              </Label>
              <Label className="flex items-center gap-2 font-normal">
                <Checkbox checked={securityIssues} onCheckedChange={(v) => setSecurityIssues(!!v)} />
                {t("securityIssues")}
              </Label>
              <Label className="flex items-center gap-2 font-normal">
                <Checkbox checked={registerWebhook} onCheckedChange={(v) => setRegisterWebhook(!!v)} />
                {t("registerWebhook")}
              </Label>
            </div>
            <LabeledField label={t("importPaths")} htmlFor="repo-paths" hint={t("importPathsHint")}>
              <Textarea id="repo-paths" rows={2} placeholder={"api/**\nweb/package-lock.json"} value={paths} onChange={(e) => setPaths(e.target.value)} />
            </LabeledField>
            <ErrorText>{error}</ErrorText>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={onClose}>
                {tc("cancel")}
              </Button>
              <Button type="submit" disabled={saving}>
                {t("link")}
              </Button>
            </DialogFooter>
          </FieldGroup>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RepoCard({ link, canManage, onChanged }: { link: RepoLink; canManage: boolean; onChanged: () => void }) {
  const t = useTranslations("repos");
  const formatDate = useFormatDate();
  const [busy, setBusy] = useState<string | null>(null);
  const [paths, setPaths] = useState(link.import_paths.join("\n"));
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [lastImport, setLastImport] = useState<RepoImport | null>(null);

  async function patch(json: Record<string, unknown>) {
    try {
      await api(`/repo-links/${link.id}`, { method: "PATCH", json });
      toast.success(t("saved"));
      onChanged();
      return true;
    } catch (err) {
      toast.error((err as Error).message);
      return false;
    }
  }

  async function run(kind: "import" | "sync") {
    setBusy(kind);
    try {
      if (kind === "import") {
        const r = await api<RepoImport>(`/repo-links/${link.id}/import`, { method: "POST" });
        setLastImport(r);
        toast.success(t("imported", { files: r.files.filter((f) => !f.error).length }));
      } else {
        const r = await api<{ tasks: number; sprints: number }>(`/repo-links/${link.id}/sync`, { method: "POST" });
        toast.success(t("synced", { tasks: r.tasks, sprints: r.sprints }));
      }
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(null);
      onChanged();
    }
  }

  async function remove() {
    if (!confirm(t("confirmDelete", { repo: link.repo }))) return;
    try {
      await api(`/repo-links/${link.id}`, { method: "DELETE" });
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <div className="grid gap-3 rounded-xl border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{link.provider === "github" ? "GitHub" : "GitLab"}</Badge>
        <a href={link.html_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium hover:underline">
          {link.repo}
          <ExternalLinkIcon className="size-3.5" />
        </a>
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <GitBranchIcon className="size-3.5" /> {link.default_branch}
        </span>
        {link.webhook_registered ? (
          <Badge variant="secondary">{t("webhookOn")}</Badge>
        ) : (
          <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-400">
            {t("webhookOff")}
          </Badge>
        )}
        {canManage && (
          <div className="ml-auto flex flex-wrap gap-2">
            <Button variant="outline" size="sm" disabled={busy !== null} onClick={() => run("import")}>
              <DownloadIcon /> {t("importNow")}
            </Button>
            {link.sync_issues && (
              <Button variant="outline" size="sm" disabled={busy !== null} onClick={() => run("sync")}>
                <ListTodoIcon /> {t("syncNow")}
              </Button>
            )}
            <Button variant="ghost" size="icon-sm" onClick={remove} title={t("delete")}>
              <Trash2Icon />
            </Button>
          </div>
        )}
      </div>
      <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">{t("lastImport")}</dt>
          <dd>
            {link.last_import_at ? formatDate(link.last_import_at) : t("never")}
            {link.last_import_sha && <span className="ml-1 font-mono text-muted-foreground">{link.last_import_sha.slice(0, 7)}</span>}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("lastEvent")}</dt>
          <dd>{link.last_event_at ? formatDate(link.last_event_at) : t("never")}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("importPaths")}</dt>
          <dd className="font-mono">{link.import_paths.length ? link.import_paths.join(", ") : t("allFiles")}</dd>
        </div>
      </dl>
      {link.last_error && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {link.last_error_at && `${formatDate(link.last_error_at)} `}
          {link.last_error}
        </p>
      )}
      {lastImport && (
        <ul className="grid gap-0.5 rounded-md bg-muted/50 px-3 py-2 font-mono text-xs">
          {lastImport.files.length === 0 && <li className="text-muted-foreground">{t("noFiles")}</li>}
          {lastImport.files.map((f) => (
            <li key={f.path} className={f.error ? "text-destructive" : undefined}>
              {f.path}: {f.error ?? t("fileResult", { added: f.result?.added ?? 0, removed: f.result?.removed ?? 0, total: f.result?.total ?? 0 })}
            </li>
          ))}
          {lastImport.removed_sources > 0 && <li>{t("removedSources", { count: lastImport.removed_sources })}</li>}
        </ul>
      )}
      {canManage && (
        <>
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <Label className="flex items-center gap-2 text-sm font-normal">
              <Checkbox checked={link.sync_issues} onCheckedChange={(v) => patch({ sync_issues: !!v })} />
              {t("syncIssues")}
            </Label>
            <Label className="flex items-center gap-2 text-sm font-normal">
              <Checkbox checked={link.security_issues} onCheckedChange={(v) => patch({ security_issues: !!v })} />
              {t("securityIssues")}
            </Label>
          </div>
          <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
            <LabeledField label={t("importPaths")} htmlFor={`paths-${link.id}`} hint={t("importPathsHint")}>
              <Textarea id={`paths-${link.id}`} rows={2} value={paths} onChange={(e) => setPaths(e.target.value)} />
            </LabeledField>
            <Button variant="outline" size="sm" onClick={() => patch({ import_paths: splitPaths(paths) })}>
              {t("savePaths")}
            </Button>
          </div>
          {showToken ? (
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={async (e) => {
                e.preventDefault();
                if (await patch({ token })) {
                  setToken("");
                  setShowToken(false);
                }
              }}
            >
              <Input className="min-w-64 flex-1" type="password" required autoComplete="off" placeholder={t("token")} value={token} onChange={(e) => setToken(e.target.value)} />
              <Button type="submit" size="sm">
                {t("saveToken")}
              </Button>
            </form>
          ) : (
            <Button variant="ghost" size="sm" className="justify-self-start" onClick={() => setShowToken(true)}>
              <KeyRoundIcon /> {t("changeToken")}
            </Button>
          )}
          {!link.webhook_registered && link.webhook_secret && (
            <div className="grid gap-2 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
              <p className="text-xs">{t(link.provider === "github" ? "manualWebhookGithub" : "manualWebhookGitlab")}</p>
              <CopyBlock text={link.webhook_url} label={t("webhookUrl")} />
              <CopyBlock text={link.webhook_secret} label={t("webhookSecret")} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
