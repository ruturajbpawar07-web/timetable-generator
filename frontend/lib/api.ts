"use client";
import { useCallback, useEffect, useState } from "react";

/* eslint-disable @typescript-eslint/no-explicit-any */
export type Any = any;

export class ApiError extends Error {
  constructor(message: string, public conflicts: Any[] = []) {
    super(message);
  }
}

export async function api<T = Any>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method: init?.method ?? (init?.body ? "POST" : "GET"),
    headers: init?.body ? { "content-type": "application/json" } : undefined,
    body: init?.body ? JSON.stringify(init.body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = data?.detail;
    throw new ApiError(typeof d === "string" ? d : Array.isArray(d) ? d.map((x: Any) => x.msg).join("; ") : `Request failed (${r.status})`, data?.conflicts);
  }
  return data as T;
}

/** GET with loading/error state.  `path=null` skips the request. */
export function useApi<T = Any>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const load = useCallback(() => {
    if (!path) return;
    setLoading(true);
    api<T>(path)
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [path]);
  useEffect(load, [load]);
  return { data, error, loading, reload: load };
}

export type Meta = {
  college: string; academic_year: string; today: string;
  days: { id: number; name: string }[];
  slots: { id: number; index: number; start: string; end: string; is_break: boolean; label: string }[];
  departments: { id: number; code: string; name: string }[];
  programs: { id: number; code: string; name: string; department_id: number }[];
  semesters: number[];
  classes: Any[]; faculty: { id: number; code: string; name: string; department_id: number }[];
  subjects: { id: number; code: string; name: string }[]; rooms: Any[];
};

let metaCache: Promise<Meta> | null = null;
export function useMeta() {
  const [meta, setMeta] = useState<Meta | null>(null);
  useEffect(() => {
    metaCache ??= api<Meta>("/meta");
    metaCache.then(setMeta).catch(() => (metaCache = null));
  }, []);
  return meta;
}
