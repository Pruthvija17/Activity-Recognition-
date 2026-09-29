import { createContext } from 'react';
import type { SystemStatus } from '../types/api';

export type Connection = 'checking' | 'online' | 'offline';

export interface SystemStatusValue {
  connection: Connection;
  online: boolean;
  status: SystemStatus | null;
  lastChecked: Date | null;
  refresh: () => void;
}

export const SystemStatusContext = createContext<SystemStatusValue>({
  connection: 'checking',
  online: false,
  status: null,
  lastChecked: null,
  refresh: () => {},
});
