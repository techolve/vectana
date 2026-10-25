"use client";

import { useCallback } from "react";

import { usePathname, useRouter } from "@/i18n/navigation";
import { LOCALE_STORAGE_KEY, type Locale } from "@/i18n/routing";
import { api, hasToken } from "@/lib/api";

/** Switch the UI language: remembered on this device and, when logged in,
 *  saved to the account so emails use it too. Query parameters are kept. */
export function useChangeLocale() {
  const pathname = usePathname();
  const router = useRouter();
  return useCallback(
    async (next: Locale) => {
      try {
        localStorage.setItem(LOCALE_STORAGE_KEY, next);
      } catch {}
      if (hasToken()) {
        await api("/auth/locale", { method: "PUT", json: { locale: next } }).catch(() => undefined);
      }
      const query = Object.fromEntries(new URLSearchParams(window.location.search));
      router.replace({ pathname, query }, { locale: next });
    },
    [pathname, router],
  );
}
