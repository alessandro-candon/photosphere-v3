# Photosphere v3 SSR Webapp

Mobile-first, desktop-capable Nuxt 4 + Firebase + Google Cloud Storage media application built with Tailwind CSS v4, `shadcn-vue` (`reka-ui`), `lucide-vue-next`, and Pinia.

## Architecture

- **Shared Domain Layer (`shared/`)**: Isomorphic DTO contracts, validation regexes, and date/epoch formatters shared across Nitro (`server/`) and Vue (`app/`).
- **Configuration (`server/utils/photosphere-config.ts`, `server/plugins/00.photosphere-config.ts`)**: Resolves `photosphere.config.json` (via `PHOTOSPHERE_CONFIG_PATH`, `./`, `../`, or `~/.photosphere/`) at runtime, hydrating per-request `useRuntimeConfig(event)` clones with `process.env.*` overrides while allowing config-free container builds (`PHOTOSPHERE_SKIP_BUILD_CONFIG=1`).
- **Dual Auth & Request Correlation (`server/middleware/00.request-logger.ts`, `server/middleware/auth.ts`, `server/services/auth.service.ts`)**:
  - Public probes: `/api/healthz`, `/api/readyz`, and `DELETE /api/auth/session`.
  - JSON & mutation APIs require `Authorization: Bearer <firebase_id_token>`, `email_verified === true`, and case-insensitive membership in `ALLOWED_EMAILS` (`ADMIN_EMAIL` for admin routes).
  - Media streaming (`GET /api/media/[hash]`) accepts either Bearer tokens or an `HttpOnly; SameSite=Lax` signed session cookie (`__ps_media`) minted via `POST /api/auth/session` (clamped to the Firebase ID token's `exp` claim and signed with `PHOTOSPHERE_SESSION_SECRET` or a persisted `.session-secret` in `mountedVolumePath`), allowing native `<img>` and `<video>` caching and HTTP `Range` (`206 Partial Content`) streaming without exposing tokens in URLs.
- **Server APIs**:
  - `GET /api/me`: returns signed-in email and role capabilities (`isAdmin`, `canEditAlbums`).
  - `POST / DELETE /api/auth/session`: mints/clears the `__ps_media` cookie for media proxy reads.
  - `GET /api/files` & `GET /api/files/[hash]`: paginated, filtered, and indexed media queries (`q`, `fileType`, `dateFrom`, `dateTo`, `memoryDate`, `album`, `notInAlbum`, `lat`/`lng`/`radiusKm` via Haversine distance, `sort=date|distance`).
  - `GET /api/map/heatmap`: viewport-bounded, filter-aware geohash cluster and raw-mode spatial aggregation.
  - `GET /api/media/[hash]?variant=thumbnail|source`: streams media backed by `Cache-Control: private, max-age=31536000, immutable`, `ETag`, `206` byte-range slice reads, and a bounded async LRU disk cache under `runtimeConfig.storage.mountedVolumePath`.
  - `GET /api/search/suggestions`: unified label and caption autocomplete with `en` fallback.
  - `GET /api/location/search`: LRU-cached, 1 req/sec rate-limited OpenStreetMap Nominatim proxy.
  - `GET / POST /api/albums` & `GET / PATCH / DELETE /api/albums/[albumName]`: paginated album summaries and conflict-safe writes to `photosphere_albums.json` using a serialized write mutex, `.meta.json` generation sidecar, and GCS `ifGenerationMatch` preconditions.
  - `POST /api/admin/refresh-database?lang=en` & `GET /api/database?lang=en`: admin-only forced reload and diagnostic JSON snapshot.
- **Frontend (`app/`)**:
  - Follows `docs/designs/frontend-design-system.md` (semantic light/dark CSS tokens with anti-FOUC head script, deterministic varied-row-span CSS Grid masonry, and a 3-tier `ui/` -> `common/` -> `organisms/` component hierarchy).
  - Routes: `/login`, `/` (Photos gallery & search/filters), `/memories` (On This Day), `/albums`, `/albums/[albumName]`, `/map` (World Map heatmap & area inspector), and `/settings`.

## Commands

```bash
pnpm install
pnpm dev
pnpm format
pnpm type-check
pnpm test
pnpm build
```
