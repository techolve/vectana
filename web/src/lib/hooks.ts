"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

/** Fetch on mount (and whenever `path` changes); `reload()` refetches. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    api<T>(path)
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [path, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { data, error, reload, loading: data === undefined && !error };
}
