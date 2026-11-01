"use client";

import { useEffect } from "react";
import { useLocale, useTranslations } from "next-intl";

import { useRouter } from "@/i18n/navigation";
import { api, setTokens } from "@/lib/api";
import { AuthLayout } from "@/components/auth-layout";

// Landing page after SSO. The API puts the app's tokens in the URL fragment,
// which never reaches a server; store them, wipe the URL and go home.
export default function SsoCallbackPage() {
  const t = useTranslations("login");
  const locale = useLocale();
  const router = useRouter();

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const access = params.get("access_token");
    const refresh = params.get("refresh_token");
    window.history.replaceState(null, "", window.location.pathname);
    if (!access || !refresh) {
      router.replace("/login?sso_error=provider");
      return;
    }
    setTokens(access, refresh);
    // Emails follow the language the user works in.
    api("/auth/locale", { method: "PUT", json: { locale } })
      .catch(() => undefined)
      .finally(() => router.replace("/"));
  }, [locale, router]);

  return (
    <AuthLayout>
      <p className="text-center text-sm text-muted-foreground">{t("ssoSigningIn")}</p>
    </AuthLayout>
  );
}
