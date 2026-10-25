"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { api, setTokens } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ErrorText, Field } from "@/components/common";

type Preview = { email: string; display_name: string | null; company_name: string };

function InviteForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api<Preview>(`/auth/invitations/${encodeURIComponent(token)}`, { auth: false })
      .then((p) => {
        setPreview(p);
        setName(p.display_name ?? "");
      })
      .catch((e) => setLoadError(e.status === 410 ? "招待の有効期限が切れています" : "招待が見つかりません"));
  }, [token]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) return setError("パスワードが一致しません");
    try {
      const t = await api<{ access_token: string; refresh_token: string }>("/auth/invitations/accept", {
        method: "POST",
        json: { token, password, display_name: name || null },
        auth: false,
      });
      setTokens(t.access_token, t.refresh_token);
      router.replace("/");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (!token || loadError) return <ErrorText>{loadError ?? "招待リンクが正しくありません"}</ErrorText>;
  if (!preview) return <p className="text-sm text-muted-foreground">確認中…</p>;

  return (
    <form onSubmit={submit} className="grid gap-4">
      <CardDescription>
        {preview.company_name} の {preview.email} としてアカウントを作成します。
      </CardDescription>
      <Field label="表示名">
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="パスワード" hint="8文字以上">
        <Input type="password" autoComplete="new-password" minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <Field label="パスワード（確認）">
        <Input type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </Field>
      <ErrorText>{error}</ErrorText>
      <Button type="submit">アカウントを作成</Button>
    </form>
  );
}

export default function InvitePage() {
  return (
    <div className="flex flex-1 items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Vectana への招待</CardTitle>
        </CardHeader>
        <CardContent>
          <Suspense>
            <InviteForm />
          </Suspense>
        </CardContent>
      </Card>
    </div>
  );
}
