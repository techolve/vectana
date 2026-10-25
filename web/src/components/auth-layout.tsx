import { ShieldIcon } from "lucide-react";

import { LocaleSwitcher } from "@/components/locale-switcher";
import { VersionLabel } from "@/components/version-label";

/** Page frame from the shadcn login-03 block: muted background, logo above the card. */
export function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex min-h-svh flex-1 flex-col items-center justify-center gap-6 bg-muted p-6 md:p-10">
      <div className="absolute top-4 right-4">
        <LocaleSwitcher />
      </div>
      <div className="flex w-full max-w-sm flex-col gap-6">
        <span className="flex items-center gap-2 self-center font-medium">
          <span className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <ShieldIcon className="size-4" />
          </span>
          Vectana
        </span>
        {children}
        <VersionLabel className="self-center" />
      </div>
    </div>
  );
}
