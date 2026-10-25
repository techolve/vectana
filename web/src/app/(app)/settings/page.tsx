"use client";

import { useState } from "react";
import { toast } from "sonner";

import { api, SEVERITIES, type Severity } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Field, PageHeader, Select } from "@/components/common";
import { useMe } from "@/components/app-shell";

type Prefs = { email_enabled: boolean; min_severity: Severity };

export default function SettingsPage() {
  const me = useMe();
  const { data } = useApi<Prefs>("/auth/notifications");
  return (
    <>
      <PageHeader title="個人設定" description={me.email} />
      <div className="grid gap-6 md:grid-cols-2">
        {data && <PrefsCard initial={data} />}
        <PasswordCard />
      </div>
    </>
  );
}

function PrefsCard({ initial }: { initial: Prefs }) {
  const [prefs, setPrefs] = useState(initial);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/auth/notifications", { method: "PUT", json: prefs });
      toast.success("保存しました");
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>メール通知</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={save} className="grid gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={prefs.email_enabled}
              onChange={(e) => setPrefs({ ...prefs, email_enabled: e.target.checked })}
            />
            アサインされたプロジェクトで脆弱性が見つかったらメールで受け取る
          </label>
          <Field label="通知する重大度" hint="重大度が不明なものは常に通知します">
            <Select
              value={prefs.min_severity}
              disabled={!prefs.email_enabled}
              onChange={(e) => setPrefs({ ...prefs, min_severity: e.target.value as Severity })}
            >
              {SEVERITIES.filter((s) => s !== "UNKNOWN").map((s) => (
                <option key={s} value={s}>
                  {s} 以上
                </option>
              ))}
            </Select>
          </Field>
          <div>
            <Button type="submit">保存</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");

  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/auth/password", { method: "POST", json: { current_password: current, new_password: next } });
      setCurrent("");
      setNext("");
      toast.success("パスワードを変更しました");
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>パスワード変更</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={save} className="grid gap-4">
          <Field label="現在のパスワード">
            <Input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
          </Field>
          <Field label="新しいパスワード" hint="8文字以上">
            <Input type="password" autoComplete="new-password" minLength={8} required value={next} onChange={(e) => setNext(e.target.value)} />
          </Field>
          <div>
            <Button type="submit">変更</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
