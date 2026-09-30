# BAS AI — Frontend

React 19 + TypeScript + Vite + Tailwind 4. See the [project README](../README.md) for setup and running.

```powershell
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check + production build into dist/
npm run lint     # oxlint
```

- Backend address: `VITE_API_URL` in `.env` (default `http://127.0.0.1:8000`, see `.env.example`); every request goes through `src/lib/api.ts`.
- `src/pages` — one component per route (lazy-loaded); `src/components` — shared UI; `src/hooks` — system status, data loading, camera.
- Activity colours (`src/lib/activityColors.ts`) are a colour-blind-validated palette in a fixed order; keep them in sync with `backend/services/analytics.py`.
