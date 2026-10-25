"use client";

import {
  BugIcon,
  Building2Icon,
  CalendarClockIcon,
  FolderIcon,
  LayoutDashboardIcon,
  MoreHorizontalIcon,
  ShieldIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";

import { Link, usePathname } from "@/i18n/navigation";
import type { Me, Project } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { NavUser } from "@/components/nav-user";

const PROJECT_LIMIT = 8;

// Based on the shadcn sidebar-07 block (collapses to icons).
export function AppSidebar({ me, ...props }: { me: Me } & React.ComponentProps<typeof Sidebar>) {
  const t = useTranslations();
  const pathname = usePathname();
  const { data: projects } = useApi<Project[]>("/projects");
  const projectId = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("id");

  const nav = [
    { href: "/", label: t("nav.dashboard"), icon: LayoutDashboardIcon },
    { href: "/projects/", label: t("nav.projects"), icon: FolderIcon },
    { href: "/vulnerabilities/", label: t("nav.vulnerabilities"), icon: BugIcon },
    { href: "/eol/", label: t("nav.eol"), icon: CalendarClockIcon },
    ...(me.can_manage_org ? [{ href: "/admin/", label: t("nav.admin"), icon: Building2Icon }] : []),
  ];
  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.replace(/\/$/, "") === href.replace(/\/$/, "");

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<Link href="/" />}>
              <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                <ShieldIcon className="size-4" />
              </div>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-medium">Vectana</span>
                <span className="truncate text-xs text-muted-foreground">{me.group_name}</span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>{t("nav.platform")}</SidebarGroupLabel>
          <SidebarMenu>
            {nav.map(({ href, label, icon: Icon }) => (
              <SidebarMenuItem key={href}>
                <SidebarMenuButton tooltip={label} isActive={isActive(href)} render={<Link href={href} />}>
                  <Icon />
                  <span>{label}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
        {projects && projects.length > 0 && (
          <SidebarGroup className="group-data-[collapsible=icon]:hidden">
            <SidebarGroupLabel>{t("nav.myProjects")}</SidebarGroupLabel>
            <SidebarMenu>
              {projects.slice(0, PROJECT_LIMIT).map((p) => {
                const issues = p.open_counts.CRITICAL + p.open_counts.HIGH + p.eol_counts.eol;
                return (
                  <SidebarMenuItem key={p.id}>
                    <SidebarMenuButton
                      isActive={pathname.startsWith("/projects/detail") && projectId === p.id}
                      render={<Link href={{ pathname: "/projects/detail/", query: { id: p.id } }} />}
                    >
                      <span
                        className={cn(
                          "size-2 shrink-0 rounded-full",
                          p.open_counts.CRITICAL || p.eol_counts.eol
                            ? "bg-red-600"
                            : p.open_counts.HIGH || p.eol_counts.approaching
                              ? "bg-orange-500"
                              : "bg-emerald-500",
                        )}
                      />
                      <span>{p.name}</span>
                    </SidebarMenuButton>
                    {issues > 0 && <SidebarMenuBadge>{issues}</SidebarMenuBadge>}
                  </SidebarMenuItem>
                );
              })}
              {projects.length > PROJECT_LIMIT && (
                <SidebarMenuItem>
                  <SidebarMenuButton className="text-sidebar-foreground/70" render={<Link href="/projects/" />}>
                    <MoreHorizontalIcon />
                    <span>{t("nav.more")}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              )}
            </SidebarMenu>
          </SidebarGroup>
        )}
      </SidebarContent>
      <SidebarFooter>
        <NavUser me={me} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
