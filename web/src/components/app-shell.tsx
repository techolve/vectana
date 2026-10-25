"use client";

import { createContext, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BugIcon,
  Building2Icon,
  FolderIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  SettingsIcon,
  ShieldIcon,
} from "lucide-react";

import { api, clearTokens, hasToken, ROLE_LABEL, type Me } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme-toggle";

const MeContext = createContext<Me | null>(null);

export function useMe(): Me {
  const me = useContext(MeContext);
  if (!me) throw new Error("useMe outside AppShell");
  return me;
}

const NAV = [
  { href: "/", label: "ダッシュボード", icon: LayoutDashboardIcon },
  { href: "/projects/", label: "プロジェクト", icon: FolderIcon },
  { href: "/vulnerabilities/", label: "脆弱性", icon: BugIcon },
];

export function AppShell({ children }: { children: React.ReactNode }) {
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
    return <div className="flex flex-1 items-center justify-center text-muted-foreground">読み込み中…</div>;
  }

  const nav = me.can_manage_org
    ? [...NAV, { href: "/admin/", label: "組織管理", icon: Building2Icon }]
    : NAV;

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <MeContext.Provider value={me}>
      <div className="flex min-h-full flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b bg-background/90 backdrop-blur">
          <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
            <Link href="/" className="flex items-center gap-2 font-semibold">
              <ShieldIcon className="size-5 text-primary" />
              Vectana
            </Link>
            <nav className="flex items-center gap-1 overflow-x-auto">
              {nav.map(({ href, label, icon: Icon }) => (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm whitespace-nowrap text-muted-foreground hover:bg-muted hover:text-foreground",
                    isActive(href) && "bg-muted text-foreground",
                  )}
                >
                  <Icon className="size-4" />
                  <span className="hidden sm:inline">{label}</span>
                </Link>
              ))}
            </nav>
            <div className="ml-auto flex items-center gap-2">
              <div className="hidden text-right text-xs leading-tight md:block">
                <div className="font-medium">{me.display_name || me.email}</div>
                <div className="text-muted-foreground">
                  {me.company_name ?? me.group_name}
                  {me.is_partner ? "（BP）" : ` / ${ROLE_LABEL[me.role]}`}
                </div>
              </div>
              <ThemeToggle />
              <Link
                href="/settings/"
                title="個人設定"
                className="rounded-md p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <SettingsIcon className="size-4" />
              </Link>
              <button
                title="ログアウト"
                className="rounded-md p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
                onClick={() => {
                  clearTokens();
                  router.replace("/login/");
                }}
              >
                <LogOutIcon className="size-4" />
              </button>
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</main>
      </div>
    </MeContext.Provider>
  );
}
