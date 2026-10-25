"use client";

import { ChevronsUpDownIcon, LanguagesIcon, LogOutIcon, MoonIcon, SettingsIcon, SunIcon } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useTheme } from "next-themes";

import { useRouter } from "@/i18n/navigation";
import { routing, type Locale } from "@/i18n/routing";
import { clearTokens, type Me } from "@/lib/api";
import { useChangeLocale } from "@/lib/use-change-locale";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from "@/components/ui/sidebar";
import { VersionLabel } from "@/components/version-label";

function initials(me: Me) {
  const source = me.display_name || me.email;
  return source.slice(0, 2).toUpperCase();
}

// Based on the shadcn sidebar-07 block's NavUser.
export function NavUser({ me }: { me: Me }) {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const changeLocale = useChangeLocale();
  const { resolvedTheme, setTheme } = useTheme();
  const { isMobile } = useSidebar();
  const subtitle = me.is_partner
    ? `${me.company_name ?? ""} (${t("labels.partner")})`
    : `${me.company_name ?? me.group_name} / ${t(`labels.role.${me.role}`)}`;

  const user = (
    <>
      <Avatar>
        <AvatarFallback>{initials(me)}</AvatarFallback>
      </Avatar>
      <div className="grid flex-1 text-left text-sm leading-tight">
        <span className="truncate font-medium">{me.display_name || me.email}</span>
        <span className="truncate text-xs text-muted-foreground">{subtitle}</span>
      </div>
    </>
  );

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger render={<SidebarMenuButton size="lg" className="aria-expanded:bg-muted" />}>
            {user}
            <ChevronsUpDownIcon className="ml-auto size-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent className="min-w-56" side={isMobile ? "bottom" : "right"} align="end" sideOffset={4}>
            <DropdownMenuGroup>
              <DropdownMenuLabel className="p-0 font-normal">
                <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">{user}</div>
              </DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuItem onClick={() => router.push("/settings/")}>
                <SettingsIcon />
                {t("common.settings")}
              </DropdownMenuItem>
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>
                  <LanguagesIcon />
                  {t("common.language")}
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent>
                  <DropdownMenuRadioGroup value={locale} onValueChange={(v) => changeLocale(v as Locale)}>
                    {routing.locales.map((l) => (
                      <DropdownMenuRadioItem key={l} value={l}>
                        {t(`locales.${l}`)}
                      </DropdownMenuRadioItem>
                    ))}
                  </DropdownMenuRadioGroup>
                </DropdownMenuSubContent>
              </DropdownMenuSub>
              <DropdownMenuItem onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
                <SunIcon className="dark:hidden" />
                <MoonIcon className="hidden dark:block" />
                {t("common.theme")}
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => {
                clearTokens();
                router.replace("/login/");
              }}
            >
              <LogOutIcon />
              {t("common.logout")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <div className="px-2 py-1">
              <VersionLabel />
            </div>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
