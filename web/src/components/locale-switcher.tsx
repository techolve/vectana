"use client";

import { LanguagesIcon } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import { routing, type Locale } from "@/i18n/routing";
import { useChangeLocale } from "@/lib/use-change-locale";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function LocaleSwitcher() {
  const t = useTranslations();
  const locale = useLocale();
  const changeLocale = useChangeLocale();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="ghost" size="icon" title={t("common.language")} />}>
        <LanguagesIcon />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuRadioGroup value={locale} onValueChange={(v) => changeLocale(v as Locale)}>
          {routing.locales.map((l) => (
            <DropdownMenuRadioItem key={l} value={l}>
              {t(`locales.${l}`)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
