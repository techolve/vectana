"use client";

import { useTranslations } from "next-intl";

import type { Upgrade, UpgradeBump } from "@/lib/api";
import { cn } from "@/lib/utils";

const BUMP_STYLE: Record<UpgradeBump, string> = {
  patch: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  minor: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  major: "bg-red-500/15 text-red-700 dark:text-red-400",
  unknown: "bg-muted text-muted-foreground",
};

/** Recommended upgrade for a package: the lowest version that fixes all its unresolved vulnerabilities. */
export function UpgradeHint({ upgrade, className }: { upgrade: Upgrade | null; className?: string }) {
  const t = useTranslations("upgrade");
  if (!upgrade) return <span className={cn("text-xs text-muted-foreground", className)}>-</span>;
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1 text-xs", className)} title={t("hint")}>
      {upgrade.version ? (
        <>
          <span className="font-mono font-medium">→ {upgrade.version}</span>
          {upgrade.bump && (
            <span className={cn("rounded px-1.5 py-0.5 text-[11px] font-semibold", BUMP_STYLE[upgrade.bump])}>
              {t(`bump.${upgrade.bump}`)}
            </span>
          )}
          {upgrade.unfixed > 0 && <span className="text-muted-foreground">{t("unfixed", { count: upgrade.unfixed })}</span>}
        </>
      ) : (
        <span className="text-muted-foreground">{t("noFix")}</span>
      )}
    </span>
  );
}
