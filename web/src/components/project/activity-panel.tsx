"use client";

import { useState } from "react";
import { CheckCircle2Icon, CircleIcon, MailIcon, PhoneIcon, Trash2Icon, UsersIcon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { ACTIVITY_KINDS, api, todayISO, type Activity, type ActivityKind, type Project, type UserBrief } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { useMe } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Empty, ErrorText, LabeledField, OptionSelect } from "@/components/common";
import { NextAction, shortDate, userLabel } from "@/components/sales/status";
import { useAssignees } from "@/components/task/task-common";

const KIND_ICON: Record<ActivityKind, typeof UsersIcon> = { meeting: UsersIcon, phone: PhoneIcon, email: MailIcon };

/** 商談メモ: meetings, calls and emails, with next actions that become tasks. */
export function ActivityPanel({ project, onChanged }: { project: Project; onChanged: () => void }) {
  const t = useTranslations("activity");
  const me = useMe();
  const { data, error, reload } = useApi<Activity[]>(`/projects/${project.id}/activities`);
  const canWrite = project.can_sell || ((project.my_level === "write" || project.my_level === "manage") && !me.is_partner);
  const open = (data ?? []).filter((a) => a.task && a.task.status !== "done");

  const refresh = () => {
    reload();
    onChanged();
  };

  async function remove(a: Activity) {
    if (!confirm(t("confirmDelete"))) return;
    try {
      await api(`/activities/${a.id}`, { method: "DELETE" });
      reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="grid content-start gap-4">
        {canWrite && <ActivityForm project={project} onSaved={refresh} />}
        <ErrorText>{error}</ErrorText>
        {data &&
          (data.length === 0 ? (
            <Empty>{t("empty")}</Empty>
          ) : (
            <ol className="relative grid gap-4 border-l pl-5">
              {data.map((a) => {
                const Icon = KIND_ICON[a.kind];
                return (
                  <li key={a.id} className="relative">
                    <span className="absolute top-0.5 -left-[31px] flex size-5 items-center justify-center rounded-full border bg-background">
                      <Icon className="size-3 text-muted-foreground" />
                    </span>
                    <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
                      <span className="font-medium tabular-nums">{a.occurred_on.replaceAll("-", "/")}</span>
                      <span className="text-xs text-muted-foreground">{t(`kind.${a.kind}`)}</span>
                      {a.participants && <span className="text-xs text-muted-foreground">・{a.participants}</span>}
                      <span className="ml-auto text-xs text-muted-foreground">{userLabel(a.created_by)}</span>
                      {canWrite && (
                        <Button variant="ghost" size="icon" className="size-6" aria-label={t("delete")} onClick={() => remove(a)}>
                          <Trash2Icon className="size-3.5" />
                        </Button>
                      )}
                    </div>
                    <p className="mt-1 text-sm whitespace-pre-wrap">{a.body}</p>
                    {a.task && (
                      <div
                        className={cn(
                          "mt-2 inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs",
                          a.task.overdue && "border-destructive/40 text-destructive",
                        )}
                      >
                        {a.task.status === "done" ? (
                          <CheckCircle2Icon className="size-3.5 text-emerald-600" />
                        ) : (
                          <CircleIcon className="size-3.5" />
                        )}
                        <span className={cn(a.task.status === "done" && "line-through opacity-70")}>{a.task.title}</span>
                        <span className="text-muted-foreground">
                          {userLabel(a.task.assignee)}
                          {a.task.due_date && ` ・ ${shortDate(a.task.due_date)}`}
                        </span>
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
          ))}
      </div>
      <div className="grid min-w-0 content-start gap-4 [&>*]:min-w-0">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("nextAction")}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <NextAction text={project.next_action} on={project.next_action_on} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("openActions", { count: open.length })}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm">
            {open.length === 0 && <p className="text-xs text-muted-foreground">{t("noOpenActions")}</p>}
            {open.map((a) => (
              <div key={a.id} className="flex min-w-0 items-start gap-2">
                <CircleIcon className={cn("mt-0.5 size-3.5 shrink-0", a.task!.overdue && "text-destructive")} />
                <div className="min-w-0">
                  <div className="truncate">{a.task!.title}</div>
                  <div className={cn("text-xs text-muted-foreground", a.task!.overdue && "text-destructive")}>
                    {userLabel(a.task!.assignee)}
                    {a.task!.due_date && ` ・ ${shortDate(a.task!.due_date)}`}
                    {a.task!.overdue && ` ${t("overdue")}`}
                  </div>
                </div>
              </div>
            ))}
            {open.length > 0 && <p className="text-xs text-muted-foreground">{t("openHint")}</p>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ActivityForm({ project, onSaved }: { project: Project; onSaved: () => void }) {
  const t = useTranslations("activity");
  const me = useMe();
  const members = useAssignees(project.id);
  const [kind, setKind] = useState<ActivityKind>("meeting");
  const [occurredOn, setOccurredOn] = useState(todayISO());
  const [participants, setParticipants] = useState("");
  const [body, setBody] = useState("");
  const [nextAction, setNextAction] = useState("");
  const [assignee, setAssignee] = useState(me.id);
  const [due, setDue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const people: UserBrief[] = [...members];
  if (!people.some((p) => p.id === me.id)) {
    people.unshift({ id: me.id, email: me.email, display_name: me.display_name, company_id: me.company_id });
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api(`/projects/${project.id}/activities`, {
        method: "POST",
        json: {
          kind,
          occurred_on: occurredOn,
          participants: participants || null,
          body,
          next_action: nextAction || null,
          next_action_assignee_id: nextAction ? assignee : null,
          next_action_due: nextAction && due ? due : null,
        },
      });
      toast.success(nextAction ? t("savedWithTask") : t("saved"));
      setBody("");
      setParticipants("");
      setNextAction("");
      setDue("");
      setError(null);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{t("add")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={save} className="grid gap-3">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex rounded-md border p-0.5" role="radiogroup" aria-label={t("kindLabel")}>
              {ACTIVITY_KINDS.map((k) => {
                const Icon = KIND_ICON[k];
                return (
                  <button
                    key={k}
                    type="button"
                    role="radio"
                    aria-checked={kind === k}
                    onClick={() => setKind(k)}
                    className={cn(
                      "flex items-center gap-1 rounded px-2.5 py-1 text-xs",
                      kind === k ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
                    )}
                  >
                    <Icon className="size-3.5" /> {t(`kind.${k}`)}
                  </button>
                );
              })}
            </div>
            <Input type="date" aria-label={t("date")} className="w-40" required value={occurredOn} onChange={(e) => setOccurredOn(e.target.value)} />
            <Input
              className="min-w-48 flex-1"
              aria-label={t("participants")}
              placeholder={t("participantsPlaceholder")}
              maxLength={300}
              value={participants}
              onChange={(e) => setParticipants(e.target.value)}
            />
          </div>
          <Textarea required rows={4} aria-label={t("body")} placeholder={t("bodyPlaceholder")} value={body} onChange={(e) => setBody(e.target.value)} />
          <div className="grid gap-3 rounded-md bg-muted/40 p-3 sm:grid-cols-[minmax(0,1fr)_180px_150px]">
            <LabeledField label={t("nextActionLabel")} htmlFor="act-next">
              <Input id="act-next" maxLength={200} placeholder={t("nextActionPlaceholder")} value={nextAction} onChange={(e) => setNextAction(e.target.value)} />
            </LabeledField>
            <LabeledField label={t("assignee")}>
              <OptionSelect
                value={assignee}
                onValueChange={setAssignee}
                disabled={!nextAction}
                options={people.map((p) => ({ value: p.id, label: userLabel(p) }))}
              />
            </LabeledField>
            <LabeledField label={t("due")} htmlFor="act-due">
              <Input id="act-due" type="date" disabled={!nextAction} value={due} onChange={(e) => setDue(e.target.value)} />
            </LabeledField>
            <p className="text-xs text-muted-foreground sm:col-span-3">{t("nextActionHint")}</p>
          </div>
          <ErrorText>{error}</ErrorText>
          <div className="flex justify-end">
            <Button type="submit" disabled={busy || !body.trim()}>
              {t("submit")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
