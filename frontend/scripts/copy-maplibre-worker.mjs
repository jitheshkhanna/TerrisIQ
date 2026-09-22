/**
 * Copy MapLibre's worker bundle into public/.
 *
 * MapLibre spawns a module Web Worker. Turbopack cannot resolve that worker chunk
 * ("chunk path empty but not in a worker"), which silently kills the worker and
 * leaves an empty map canvas. Serving the worker as a static asset and pointing
 * MapLibre at it with setWorkerUrl sidesteps the bundler entirely, and works the
 * same under Turbopack, webpack, dev and production.
 *
 * The worker imports ./maplibre-gl-shared.mjs relatively, so both files ship.
 */
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const from = join(root, "node_modules", "maplibre-gl", "dist");
const to = join(root, "public", "maplibre");

mkdirSync(to, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(join(from, file), join(to, file));
  console.log(`copied ${file} -> public/maplibre/${file}`);
}
