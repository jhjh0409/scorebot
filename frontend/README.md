# scorebot frontend

React + Vite SPA implementing the design in `../docs/design/scorebot-A.dc.html`.

```bash
pnpm install
pnpm dev        # vite on :5173, proxies /api to uvicorn on :8000
pnpm build      # emits dist/, served by FastAPI in production
pnpm vitest run # unit tests for the view logic (src/lib.ts)
```

Two views (state-switched, no router): **Screen** (preset picker, multi-PDF drop
zone, live results table polling every 2s, detail drawer) and **Presets**
(cards + editor for dimensions/weights/guidance/enrichments). All API shapes in
`src/types.ts` mirror the backend Pydantic models.
