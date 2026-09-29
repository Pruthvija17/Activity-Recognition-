import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api } from '../lib/api';
import { STATUS_POLL_MS } from '../lib/config';
import { SystemStatusContext, type Connection } from '../context/systemStatus';
import type { SystemStatus } from '../types/api';

/** Polls /api/system/status and shares the result with the whole app. */
export default function SystemStatusProvider({ children }: { children: ReactNode }) {
  const [connection, setConnection] = useState<Connection>('checking');
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const s = await api.getSystemStatus();
        if (cancelled) return;
        setStatus(s);
        setConnection('online');
      } catch {
        if (cancelled) return;
        setStatus(null);
        setConnection('offline');
      }
      if (!cancelled) setLastChecked(new Date());
    };
    check();
    const id = setInterval(check, STATUS_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [nonce]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  const value = useMemo(
    () => ({ connection, online: connection === 'online', status, lastChecked, refresh }),
    [connection, status, lastChecked, refresh],
  );

  return <SystemStatusContext.Provider value={value}>{children}</SystemStatusContext.Provider>;
}
