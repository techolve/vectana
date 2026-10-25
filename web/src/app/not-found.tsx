import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3">
      <p className="text-muted-foreground">ページが見つかりません</p>
      <Link href="/" className="text-sm underline">
        ダッシュボードへ
      </Link>
    </div>
  );
}
