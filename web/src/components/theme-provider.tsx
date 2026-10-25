"use client";

import * as React from "react";
import { ThemeProvider as NextThemesProvider } from "next-themes";

export function ThemeProvider({
  children,
  ...props
}: React.ComponentProps<typeof NextThemesProvider>) {
  return (
    <NextThemesProvider
      {...props}
      scriptProps={{
        // next-themes injects an inline <script> to set the theme before
        // paint. This Next.js version errors when a React render produces a
        // <script>, so mark it inert on the client (server runs it, client
        // ignores it) per the "Preventing Flash" guide.
        type: typeof window === "undefined" ? "text/javascript" : "text/plain",
        suppressHydrationWarning: true,
        ...props.scriptProps,
      }}
    >
      {children}
    </NextThemesProvider>
  );
}
