"use client";

import { createContext, useContext, useEffect, useState } from "react";
import {
  BugIcon,
  Building2Icon,
  FolderIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  SettingsIcon,
  ShieldIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";

import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { api, clearTokens, hasToken, type Me } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { ThemeToggle } from "@/components/theme-toggle";
import { VersionLabel } from "@/components/version-label";

const MeContext = createContext<Me | null>(null);

export function useMe(): Me {
  const me = useContext(MeContext);
  if (!me) throw new Error("useMe outside AppShell");
  return me;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const t = useTranslations();
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    if (!hasToken()) {
      router.replace("/login/");
      return;
    }
    api<Me>("/auth/me").then(setMe).catch(() => router.replace("/login/"));
  }, [router]);

  if (!me) {
    return <div className="flex flex-1 items-center justify-center text-muted-foreground">{t("common.loading")}</div>;
  }

  const nav = [
    { href: "/", label: t("nav.dashboard"), icon: LayoutDashboardIcon },
    { href: "/projects/", label: t("nav.projects"), icon: FolderIcon },
    { href: "/vulnerabilities/", label: t("nav.vulnerabilities"), icon: BugIcon },
    ...(me.can_manage_org ? [{ href: "/admin/", label: t("nav.admin"), icon: Building2Icon }] : []),
  ];
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href.replace(/\/$/, "")));

  return (
    <MeContext.Provider value={me}>
      <div className="flex min-h-full flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b bg-background/90 backdrop-blur">
          <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
            <Link href="/" className="flex items-center gap-2 font-semibold">
              <span className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <ShieldIcon className="size-4" />
              </span>
              Vectana
            </Link>
            <nav className="flex items-center gap-1 overflow-x-auto">
              {nav.map(({ href, label, icon: Icon }) => (
                <Button
                  key={href}
                  variant="ghost"
                  size="sm"
                  className={cn("text-muted-foreground", isActive(href) && "bg-muted text-foreground")}
                  nativeButton={false}
                  render={<Link href={href} />}
                >
                  <Icon />
                  <span className="hidden sm:inline">{label}</span>
                </Button>
              ))}
            </nav>
            <div className="ml-auto flex items-center gap-1">
              <div className="mr-2 hidden text-right text-xs leading-tight md:block">
                <div className="font-medium">{me.display_name || me.email}</div>
                <div className="text-muted-foreground">
                  {me.company_name ?? me.group_name}
                  {me.is_partner ? ` (${t("labels.partner")})` : ` / ${t(`labels.role.${me.role}`)}`}
                </div>
              </div>
              <LocaleSwitcher />
              <ThemeToggle />
              <Button
                variant="ghost"
                size="icon"
                title={t("common.settings")}
                nativeButton={false}
                render={<Link href="/settings/" />}
              >
                <SettingsIcon />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                title={t("common.logout")}
                onClick={() => {
                  clearTokens();
                  router.replace("/login/");
                }}
              >
                <LogOutIcon />
              </Button>
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</main>
        <footer className="mx-auto w-full max-w-7xl px-4 pb-4 text-right">
          <VersionLabel />
        </footer>
      </div>
    </MeContext.Provider>
  );
}
