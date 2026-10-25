import { LocaleRedirect } from "@/components/locale-redirect";
import "./globals.css";

// Served by the API for any unknown path. Unprefixed paths are redirected to
// the user's locale; a missing page under a locale goes to that locale's home.
export default function NotFound() {
  return (
    <html lang="ja">
      <body className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
        <LocaleRedirect />
        Redirecting…
      </body>
    </html>
  );
}
