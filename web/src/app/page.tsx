import { LocaleRedirect } from "@/components/locale-redirect";
import "./globals.css";

export default function RootPage() {
  return (
    <html lang="ja">
      <body>
        <LocaleRedirect />
      </body>
    </html>
  );
}
