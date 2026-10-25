"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { api, hasToken, type Me } from "@/lib/api";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";

const MeContext = createContext<Me | null>(null);
const CrumbContext = createContext<(label: string | null) => void>(() => {});

export function useMe(): Me {
  const me = useContext(MeContext);
  if (!me) throw new Error("useMe outside AppShell");
  return me;
}

/** Let a page add its own last breadcrumb (e.g. the project name). */
export function usePageCrumb(label: string | null | undefined) {
  const set = useContext(CrumbContext);
  useEffect(() => {
    set(label ?? null);
    return () => set(null);
  }, [label, set]);
}

const SECTIONS = {
  "/projects": "nav.projects",
  "/vulnerabilities": "nav.vulnerabilities",
  "/eol": "nav.eol",
  "/admin": "nav.admin",
  "/settings": "common.settings",
} as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const t = useTranslations();
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [crumb, setCrumb] = useState<string | null>(null);

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

  const sectionPath = (Object.keys(SECTIONS) as (keyof typeof SECTIONS)[]).find((p) => pathname.startsWith(p));

  return (
    <MeContext.Provider value={me}>
      <CrumbContext.Provider value={setCrumb}>
        <SidebarProvider>
          <AppSidebar me={me} />
          <SidebarInset>
            <header className="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12">
              <div className="flex items-center gap-2 px-4">
                <SidebarTrigger className="-ml-1" />
                <Separator orientation="vertical" className="mr-2 data-vertical:h-4 data-vertical:self-auto" />
                <Breadcrumb>
                  <BreadcrumbList>
                    <BreadcrumbItem className="hidden md:block">
                      {sectionPath ? (
                        <BreadcrumbLink render={<Link href="/" />}>{me.group_name}</BreadcrumbLink>
                      ) : (
                        <BreadcrumbPage>{t("nav.dashboard")}</BreadcrumbPage>
                      )}
                    </BreadcrumbItem>
                    {sectionPath && (
                      <>
                        <BreadcrumbSeparator className="hidden md:block" />
                        <BreadcrumbItem>
                          {crumb ? (
                            <BreadcrumbLink render={<Link href={`${sectionPath}/`} />}>
                              {t(SECTIONS[sectionPath])}
                            </BreadcrumbLink>
                          ) : (
                            <BreadcrumbPage>{t(SECTIONS[sectionPath])}</BreadcrumbPage>
                          )}
                        </BreadcrumbItem>
                      </>
                    )}
                    {crumb && (
                      <>
                        <BreadcrumbSeparator />
                        <BreadcrumbItem>
                          <BreadcrumbPage>{crumb}</BreadcrumbPage>
                        </BreadcrumbItem>
                      </>
                    )}
                  </BreadcrumbList>
                </Breadcrumb>
              </div>
            </header>
            <main className="flex flex-1 flex-col gap-4 p-4 pt-0">{children}</main>
          </SidebarInset>
        </SidebarProvider>
      </CrumbContext.Provider>
    </MeContext.Provider>
  );
}
