"use client";

import { useEffect, useState } from "react";

import { fetchBackendStatus } from "@/lib/api";
import type { BackendStatus } from "@/lib/types";

export function useBackendStatus(enabled = true) {
  const [status, setStatus] = useState<BackendStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const nextStatus = await fetchBackendStatus();
      setStatus(nextStatus);
      return nextStatus;
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Failed to fetch backend status.";
      setError(message);
      throw caught;
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!enabled) {
      return;
    }

    let cancelled = false;
    void fetchBackendStatus()
      .then((nextStatus) => {
        if (!cancelled) {
          setStatus(nextStatus);
          setError(null);
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          const message = caught instanceof Error ? caught.message : "Failed to fetch backend status.";
          setError(message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [enabled]);

  const isLoading = loading || (enabled && status === null && error === null);

  return { status, error, loading: isLoading, refresh, setStatus };
}
