// Single source of truth for backend addresses. Override with VITE_API_URL in frontend/.env.
// Default is 127.0.0.1 (not localhost): on Windows `localhost` resolves to IPv6 ::1 first,
// while the backend listens on IPv4.
const rawApiUrl = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

export const API_URL = rawApiUrl.replace(/\/+$/, '');
export const WS_URL = API_URL.replace(/^http/, 'ws');

export const STATUS_POLL_MS = 5000;
