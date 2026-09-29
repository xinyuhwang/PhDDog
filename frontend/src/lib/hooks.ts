"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "./api";

/** Fetch `path`; re-fetch every `intervalMs` while `shouldPoll(data)` is true. */
export function useApi<T>(path: string | null, shouldPoll?: (data: T) => boolean, intervalMs = 1500) {
  const [data, setData] = useState<T | undefined>();
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!path) return;
    try {
      setData(await api.get<T>(path));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [path]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial fetch
    reload();
  }, [reload]);

  const polling = data !== undefined && !!shouldPoll?.(data);
  useEffect(() => {
    if (!polling) return;
    const t = setTimeout(reload, intervalMs);
    return () => clearTimeout(t);
  }, [polling, data, reload, intervalMs]);

  return { data, error, reload, setData };
}
