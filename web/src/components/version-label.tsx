"use client";

import { useTranslations } from "next-intl";

import type { Health } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";

/** Version of the running API, so it always matches the deployed image. */
export function useAppVersion(): string | null {
  const { data } = useApi<Health>("/health");
  return data?.version ?? null;
}

/** "Vectana v0.1.5" */
export function VersionLabel({ className }: { className?: string }) {
  const t = useTranslations("common");
  const version = useAppVersion();
  if (!version) return null;
  return (
    <span className={cn("text-xs text-muted-foreground", className)} title={t("version", { version })}>
      Vectana v{version}
    </span>
  );
}
