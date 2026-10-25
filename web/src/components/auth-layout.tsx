"use client";

import { ShieldIcon } from "lucide-react";

import { LocaleSwitcher } from "@/components/locale-switcher";
import { useAppVersion, VersionLabel } from "@/components/version-label";

/** Page frame from the shadcn login-02 block: form on the left, and on the
 *  right (wide screens) the app name and running version instead of an image.
 *  On narrow screens the right panel is hidden, so the name and version move
 *  to the left column. */
export function AuthLayout({ children }: { children: React.ReactNode }) {
  const version = useAppVersion();
  return (
    <div className="grid min-h-svh flex-1 lg:grid-cols-2">
      <div className="flex flex-col gap-4 p-6 md:p-10">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-2 font-medium lg:invisible">
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
        <VersionLabel className="self-center lg:hidden" />
      </div>
      <div className="relative hidden flex-col items-center justify-center gap-4 bg-muted p-10 lg:flex">
        <span className="flex size-16 items-center justify-center rounded-2xl bg-primary text-primary-foreground">
          <ShieldIcon className="size-9" />
        </span>
        <h2 className="text-5xl font-bold tracking-tight">Vectana</h2>
        {version && <p className="font-mono text-sm text-muted-foreground">v{version}</p>}
      </div>
    </div>
  );
}
