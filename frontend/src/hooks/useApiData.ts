import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, toApiError } from '../lib/api';
import { MESSAGES } from '../lib/messages';
import { useSystemStatus } from './useSystemStatus';

const OFFLINE_ERROR = new ApiError('offline', MESSAGES.backendOffline);

interface ApiDataState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
}

/**
 * Loads data from the backend once it is reachable, and again whenever it comes back
 * online, `key` changes, or `reload()` is called. Stale data is kept while reloading.
 */
export function useApiData<T>(loader: () => Promise<T>, key: string = '') {
  const { online, connection } = useSystemStatus();
  const loaderRef = useRef(loader);
  const [state, setState] = useState<ApiDataState<T>>({ data: null, error: null, loading: true });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    loaderRef.current = loader;
  });

  useEffect(() => {
    if (!online) return;
    let cancelled = false;
    loaderRef.current().then(
      (data) => {
        if (!cancelled) setState({ data, error: null, loading: false });
      },
      (err) => {
        if (!cancelled) setState((s) => ({ data: s.data, error: toApiError(err), loading: false }));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [online, key, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  // While the backend is known to be down, report that instead of an endless "loading".
  const error = state.error ?? (connection === 'offline' ? OFFLINE_ERROR : null);
  const loading = state.loading && connection !== 'offline';

  return { ...state, error, loading, reload };
}
