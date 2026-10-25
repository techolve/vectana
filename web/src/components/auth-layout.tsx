"use client";

import { BugIcon, CalendarClockIcon, ShieldIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { LocaleSwitcher } from "@/components/locale-switcher";
import { VersionLabel } from "@/components/version-label";

/** Page frame from the shadcn login-02 block: form on the left, a panel on the right.
 *  The block's placeholder image is replaced by a short product description. */
export function AuthLayout({ children }: { children: React.ReactNode }) {
  const t = useTranslations();
  return (
    <div className="grid min-h-svh flex-1 lg:grid-cols-2">
      <div className="flex flex-col gap-4 p-6 md:p-10">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-2 font-medium">
            <span className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <ShieldIcon className="size-4" />
            </span>
            Vectana
          </span>
          <LocaleSwitcher />
        </div>
        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-xs">{children}</div>
        </div>
        <VersionLabel className="self-center md:self-start" />
      </div>
      <div className="relative hidden flex-col justify-end gap-6 bg-muted p-10 lg:flex">
        <div className="flex gap-3 text-muted-foreground">
          <BugIcon className="size-6" />
          <CalendarClockIcon className="size-6" />
        </div>
        <p className="max-w-md text-lg font-medium text-balance">{t("login.tagline")}</p>
      </div>
    </div>
  );
}
