// The real layout lives in [locale]/layout.tsx; root pages render their own <html>.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
