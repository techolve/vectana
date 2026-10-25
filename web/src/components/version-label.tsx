"use client";

import { useTranslations } from "next-intl";

import type { Health } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";

/** "Vectana v0.1.3", read from the running API so it always matches the deployed image. */
export function VersionLabel({ className }: { className?: string }) {
  const t = useTranslations("common");
  const { data } = useApi<Health>("/health");
  if (!data) return null;
  return (
    <span className={cn("text-xs text-muted-foreground", className)} title={t("version", { version: data.version })}>
      Vectana v{data.version}
    </span>
  );
}
