"use client";

import { useRef, useState } from "react";
import { Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import {
  api,
  isOverdue,
  MATCH_STATUSES,
  type MatchDetail,
  type MatchEvent,
  type MatchStatus,
  type Member,
  type Project,
  type UserBrief,
} from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { useMe } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { ErrorText, LabeledField, OptionSelect, SeverityBadge, useFormatDate } from "@/components/common";

export function userName(u: Pick<UserBrief, "email" | "display_name"> | null | undefined): string {
  return u ? u.display_name || u.email : "";
}

/** Side panel for one vulnerability: triage fields, comments and history. */
export function MatchSheet({
  matchId,
  onClose,
  onChanged,
}: {
  matchId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const t = useTranslations();
  const { data: match, error, reload } = useApi<MatchDetail>(`/vulnerabilities/${matchId}`);

  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full gap-0 overflow-y-auto data-[side=right]:sm:max-w-xl">
        {error && <ErrorText>{error}</ErrorText>}
        {!match ? (
          <SheetHeader>
            <SheetTitle>{t("common.loading")}</SheetTitle>
          </SheetHeader>
        ) : (
          <MatchSheetBody
            match={match}
            onChanged={() => {
              reload();
              onChanged();
            }}
          />
        )}
      </SheetContent>
    </Sheet>
  );
}

function MatchSheetBody({ match, onChanged }: { match: MatchDetail; onChanged: () => void }) {
  const t = useTranslations();
  const me = useMe();
  const formatDate = useFormatDate();
  const { data: project } = useApi<Project>(`/projects/${match.project_id}`);
  const canWrite = project?.my_level === "write" || project?.my_level === "manage";
  const canManage = project?.my_level === "manage";
  const { data: members } = useApi<Member[]>(`/projects/${match.project_id}/members`);
  const [comment, setComment] = useState("");
  const [posting, setPosting] = useState(false);

  // People who can triage: owners and members. Keep the current assignee and
  // the caller selectable even when they have access through an admin role.
  const candidates = new Map<string, string>();
  for (const m of members ?? []) {
    if (m.role !== "viewer") candidates.set(m.user_id, userName(m));
  }
  if (canWrite && !candidates.has(me.id)) candidates.set(me.id, userName(me));
  if (match.assignee) candidates.set(match.assignee.id, userName(match.assignee));
  const assigneeOptions = [
    { value: "", label: t("triage.unassigned") },
    ...[...candidates.entries()].map(([value, label]) => ({
      value,
      label: value === me.id ? t("triage.meSuffix", { name: label }) : label,
    })),
  ];

  async function update(json: Record<string, unknown>) {
    try {
      await api(`/vulnerabilities/${match.id}`, { method: "PATCH", json });
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  async function postComment(e: React.FormEvent) {
    e.preventDefault();
    if (!comment.trim()) return;
    setPosting(true);
    try {
      await api(`/vulnerabilities/${match.id}/comments`, {
        method: "POST",
        json: { body: comment },
      });
      setComment("");
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setPosting(false);
    }
  }

  async function deleteComment(ev: MatchEvent) {
    if (!confirm(t("triage.confirmDelete"))) return;
    try {
      await api(`/vulnerabilities/${match.id}/comments/${ev.id}`, {
        method: "DELETE",
      });
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  const overdue = isOverdue(match);

  // Date inputs report every segment edit, so save after a pause (or on blur).
  const dueTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  function saveDue(value: string) {
    clearTimeout(dueTimer.current);
    // Ignore half-typed years such as 0002-…
    if (value !== (match.due_date ?? "") && (value === "" || value >= "2000-01-01")) {
      update({ due_date: value || null });
    }
  }

  function describeChange(ev: MatchEvent): string {
    const none = t("triage.emptyValue");
    if (ev.kind === "status") {
      const label = (v: string | null) => (v ? t(`labels.status.${v as MatchStatus}`) : none);
      return t("triage.changedStatus", {
        from: label(ev.old_value),
        to: label(ev.new_value),
      });
    }
    if (ev.kind === "assignee") {
      const label = (u: UserBrief | null, raw: string | null) => (u ? userName(u) : raw ? t("triage.someone") : none);
      return t("triage.changedAssignee", {
        from: label(ev.old_user, ev.old_value),
        to: label(ev.new_user, ev.new_value),
      });
    }
    return t("triage.changedDueDate", {
      from: ev.old_value ?? none,
      to: ev.new_value ?? none,
    });
  }

  return (
    <>
      <SheetHeader className="pr-12">
        <div className="flex items-center gap-2">
          <SeverityBadge severity={match.severity} />
          {match.cvss_score != null && <span className="text-xs text-muted-foreground">CVSS {match.cvss_score}</span>}
        </div>
        <SheetTitle className="font-mono">
          <a
            href={`https://osv.dev/vulnerability/${match.vuln_id}`}
            target="_blank"
            rel="noreferrer"
            className="hover:underline"
          >
            {match.vuln_id}
          </a>
          {match.aliases.length > 0 && (
            <span className="ml-1 text-xs font-normal text-muted-foreground">({match.aliases.join(", ")})</span>
          )}
        </SheetTitle>
        {match.summary && <SheetDescription>{match.summary}</SheetDescription>}
      </SheetHeader>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 px-4 pb-4 text-xs">
        <dt className="text-muted-foreground">{t("matches.project")}</dt>
        <dd>
          <Link
            href={{
              pathname: "/projects/detail/",
              query: { id: match.project_id },
            }}
            className="hover:underline"
          >
            {match.project_name}
          </Link>
        </dd>
        <dt className="text-muted-foreground">{t("matches.package")}</dt>
        <dd className="font-mono">
          {match.ecosystem} / {match.package_name}@{match.package_version}
        </dd>
        <dt className="text-muted-foreground">{t("matches.fixed")}</dt>
        <dd className="font-mono">{match.fixed_version ?? "-"}</dd>
        <dt className="text-muted-foreground">{t("matches.detected")}</dt>
        <dd>{formatDate(match.first_seen_at)}</dd>
      </dl>

      <Separator />

      <div className="grid gap-4 p-4 sm:grid-cols-3">
        <LabeledField label={t("matches.status")}>
          <OptionSelect
            value={match.status}
            disabled={!canWrite}
            onValueChange={(v) => v !== match.status && update({ status: v })}
            options={MATCH_STATUSES.map((s) => ({
              value: s,
              label: t(`labels.status.${s}`),
            }))}
          />
        </LabeledField>
        <LabeledField label={t("triage.assignee")}>
          <OptionSelect
            value={match.assignee?.id ?? ""}
            disabled={!canWrite}
            onValueChange={(v) => v !== (match.assignee?.id ?? "") && update({ assignee_id: v || null })}
            options={assigneeOptions}
          />
        </LabeledField>
        <LabeledField label={t("triage.dueDate")} htmlFor="due-date">
          <Input
            id="due-date"
            type="date"
            disabled={!canWrite}
            // Remount when the saved value changes so the field shows it.
            key={match.due_date ?? ""}
            defaultValue={match.due_date ?? ""}
            onChange={(e) => {
              const value = e.target.value;
              clearTimeout(dueTimer.current);
              dueTimer.current = setTimeout(() => saveDue(value), 800);
            }}
            onBlur={(e) => saveDue(e.target.value)}
            className={cn(overdue && "border-destructive text-destructive")}
          />
          {overdue && <p className="text-xs text-destructive">{t("triage.overdue")}</p>}
        </LabeledField>
      </div>

      <Separator />

      <div className="grid gap-3 p-4">
        <h3 className="text-sm font-medium">{t("triage.activity")}</h3>
        {match.events.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t("triage.noActivity")}</p>
        ) : (
          <ol className="grid gap-3">
            {match.events.map((ev) => (
              <li key={ev.id} className="text-sm">
                {ev.kind === "comment" ? (
                  <div className="rounded-lg border p-3">
                    <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">{userName(ev.user) || t("triage.someone")}</span>
                      <span>{formatDate(ev.created_at)}</span>
                      {(ev.user?.id === me.id || canManage) && (
                        <Button
                          variant="ghost"
                          size="icon-xs"
                          className="ml-auto"
                          aria-label={t("common.delete")}
                          onClick={() => deleteComment(ev)}
                        >
                          <Trash2Icon />
                        </Button>
                      )}
                    </div>
                    <p className="break-words whitespace-pre-wrap">{ev.body}</p>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">{userName(ev.user) || t("triage.someone")}</span>{" "}
                    {describeChange(ev)} <span className="ml-1">{formatDate(ev.created_at)}</span>
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
        {canWrite && (
          <form onSubmit={postComment} className="grid gap-2">
            <Textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder={t("triage.commentPlaceholder")}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) postComment(e);
              }}
            />
            <div className="flex justify-end">
              <Button type="submit" disabled={posting || !comment.trim()}>
                {t("triage.post")}
              </Button>
            </div>
          </form>
        )}
      </div>
    </>
  );
}
