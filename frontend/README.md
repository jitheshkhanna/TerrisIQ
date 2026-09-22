# ChennaiTerraRisk — frontend

Next.js + MapLibre GL UI. See the [project README](../README.md) for the full picture.

```bash
npm install
npm run dev     # http://localhost:3000
```

Requires the backend running on `:8000` (`cd ../backend && make serve`). `/api/*` is
proxied there via `next.config.ts`, so there is no CORS configuration.

`npm run predev`/`prebuild` copy MapLibre's Web Worker into `public/maplibre/`.
Turbopack cannot resolve that worker chunk from the package, which silently leaves a
blank map canvas; serving it statically and calling `setWorkerUrl` sidesteps the bundler.
Do not remove that step.
