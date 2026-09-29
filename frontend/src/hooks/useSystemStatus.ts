import { useContext } from 'react';
import { SystemStatusContext } from '../context/systemStatus';

export function useSystemStatus() {
  return useContext(SystemStatusContext);
}
