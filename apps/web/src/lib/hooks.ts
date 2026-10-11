"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
export function useResource<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const mounted = useRef(false);
  const activePath = useRef<string | null>(null);
  const reload = useCallback(async () => {
    if (!mounted.current || activePath.current !== path) return;
    const request = ++generation.current;
    const current = () => mounted.current && generation.current === request;
    setLoading(true);
    setError(undefined);
    try {
      const response = await api<T>(path);
      if (current()) setData(response);
    } catch (e) {
      if (current()) setError(e);
    } finally {
      if (current()) setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    mounted.current = true;
    activePath.current = path;
    void reload();
    return () => {
      mounted.current = false;
      activePath.current = null;
      generation.current++;
    };
  }, [reload, path]);
  return { data, error, loading, reload, setData };
}

// Refresh persisted domain records without remounting editors or clearing local
// drafts. The workspace emits this after an authorized notification read,
// either from SSE or its polling fallback.
export function useDomainRefresh(refresh: () => void) {
  const latest = useRef(refresh);
  useEffect(() => {
    latest.current = refresh;
  }, [refresh]);
  useEffect(() => {
    const update = () => latest.current();
    window.addEventListener("vector:domain-updated", update);
    return () => window.removeEventListener("vector:domain-updated", update);
  }, []);
}
