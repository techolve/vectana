import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["ja", "en"],
  defaultLocale: "ja",
  // Static export has no middleware, so every URL carries its locale.
  localePrefix: "always",
});

export type Locale = (typeof routing.locales)[number];

export const LOCALE_STORAGE_KEY = "vectana.locale";
