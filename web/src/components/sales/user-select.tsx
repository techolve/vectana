"use client";

import { useTranslations } from "next-intl";

import type { UserBrief } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { OptionSelect } from "@/components/common";

/** Pick an active user of the group (not available to partner users). */
export function UserSelect({
  value,
  onChange,
  current,
  disabled,
}: {
  value: string;
  onChange: (id: string) => void;
  current?: UserBrief | null;
  disabled?: boolean;
}) {
  const t = useTranslations();
  const { data } = useApi<UserBrief[]>("/users/directory");
  const users = [...(data ?? [])];
  if (current && !users.some((u) => u.id === current.id)) users.unshift(current);
  return (
    <OptionSelect
      value={value}
      onValueChange={onChange}
      disabled={disabled}
      options={[
        { value: "", label: t("common.noneOption") },
        ...users.map((u) => ({ value: u.id, label: u.display_name || u.email })),
      ]}
    />
  );
}
