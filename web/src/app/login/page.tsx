"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldIcon } from "lucide-react";

import { api, setTokens } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ErrorText, Field } from "@/components/common";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const t = await api<{ access_token: string; refresh_token: string }>("/auth/login", {
        method: "POST",
        json: { email, password },
        auth: false,
      });
      setTokens(t.access_token, t.refresh_token);
      router.replace("/");
    } catch {
      setError("メールアドレスまたはパスワードが違います");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-1 items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldIcon className="size-5 text-primary" /> Vectana にログイン
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid gap-4">
            <Field label="メールアドレス">
              <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="パスワード">
              <Input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            <ErrorText>{error}</ErrorText>
            <Button type="submit" disabled={busy}>
              ログイン
            </Button>
            <p className="text-xs text-muted-foreground">アカウントは管理者からの招待で作成されます。</p>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
