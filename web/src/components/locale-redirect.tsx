"use client";

import { useEffect } from "react";
import { LOCALE_STORAGE_KEY, routing } from "@/i18n/routing";

/** Pick the saved locale, else the browser's, and move to the same path under it.
 *  Keeps old unprefixed links (e.g. invitation emails: /invite/?token=...) working. */
export function preferredLocale(): string {
  try {
    const saved = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (saved && (routing.locales as readonly string[]).includes(saved)) return saved;
  } catch {}
  return navigator.language?.toLowerCase().startsWith("ja") ? "ja" : "en";
}

export function LocaleRedirect() {
  useEffect(() => {
    const { pathname, search, hash } = window.location;
    const first = pathname.split("/")[1];
    if ((routing.locales as readonly string[]).includes(first)) {
      window.location.replace(`/${first}/`);
      return;
    }
    const path = pathname.endsWith("/") ? pathname : `${pathname}/`;
    window.location.replace(`/${preferredLocale()}${path}${search}${hash}`);
  }, []);
  return null;
}
