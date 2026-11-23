# Photosphere v3 SSR Webapp — Feature-by-Feature Recreation Roadmap

*   **Author:** alessandro-candon
*   **Status:** Proposed
*   **Date:** 2026-11-22

--------------------------------------------------------------------------------

## Overview

This document defines the phased, feature-by-feature recreation plan for the Photosphere v3 web application inside `ssr/` on Nuxt 4, Vue 3, Pinia, Tailwind CSS, `shadcn-vue`, Firebase Auth, and Google Cloud Storage (GCS).

It pairs Nuxt server APIs, caching and authentication boundaries, and client state/route lifecycles into sequential vertical slices that transform the current login-test skeleton (`/` raw JSON viewer and `/login`) into a mobile-first, desktop-capable, Google Photos-style personal media application. Visual tokens, typography, spacing, light/dark CSS variables, and data-agnostic organism interfaces are owned separately by the companion Frontend Design System specification (`./frontend-design-system.md`); this roadmap references those organisms strictly by canonical name.

## The Problem

The current `ssr/` application validates Firebase Google Sign-In and GCS connectivity, but is only a 2-page raw JSON inspector (`GET /api/database` dumps the entire unpaginated media database, labels, captions, and albums to the browser). It cannot display photos or videos, filter or paginate media on the server, browse memories or albums, or manage albums.

Meanwhile, the older Quasar-based `photosphere-v2/ssr` application cannot be copied directly into v3 because:

1. **Schema and bucket mismatch:** v3 uses snake_case fields, nullable timestamps/coordinates/thumbnails, string `file_type` enums (`"FILE" | "IMAGE" | "VIDEO"`), and a two-bucket GCS split (`data_bucket` on `STANDARD`, `media_bucket` on `ARCHIVE`), whereas v2 assumed camelCase, numeric enums, and a single bucket.
2. **Media auth and `ARCHIVE` cost hazards:** Native `<img>` and `<video>` elements cannot send `Authorization: Bearer` headers. v2 worked around this with JS `fetch()` + blob URLs (breaking browser caching and video seeking) and bypassed disk caching on HTTP `Range` requests, which triggers repeated GCS `ARCHIVE` retrieval fees.
3. **Broken v2 query and filter patterns:** v2 passed full album `hashList` / `excludeHashList` arrays in `GET` query strings (hitting URL length limits on large albums), had a location filter bug where `null` geohashes falsely matched location queries, used a hardcoded precision-5 geohash that ignored radius, and called OpenStreetMap Nominatim with no caching, timeout, or rate limiting.
4. **Missing album write path and skeleton bugs:** v3 currently has no GCS write path or concurrency guard for editing `photosphere_albums.json`, `/api/readyz` is blocked by auth middleware, and `auth.ts` runs before `request-logger.ts`, dropping request correlation on auth failures.

Recreating the application in ordered vertical slices eliminates these defects upfront while keeping every slice small, testable, and aligned with the v3 contracts in `contracts/`.

## Goals

*   **Replace the login-test skeleton** with a mobile-first, responsive, Google Photos-style web application supporting toggleable light/dark themes on Nuxt 4, Vue 3, Pinia, Tailwind CSS, `shadcn-vue`, Firebase Auth, and GCS.
*   **Serve all collections through server-side paginated and filtered APIs** backed by `contracts/` schemas and pre-built in-memory indexes, eliminating client-sent hash lists (`hashList` / `excludeHashList`) and multi-megabyte JSON dumps to the browser.
*   **Minimize GCS `ARCHIVE` retrieval costs** by authenticating native `<img>` and `<video>` requests via a scoped `HttpOnly` Firebase Session Cookie, serving content-addressed media with immutable browser cache headers, and maintaining a bounded persistent LRU disk cache under `runtimeConfig.storage.mountedVolumePath`.
*   **Keep the media database strictly read-only from the web UI** (admin-triggered cache refresh only) while **enabling conflict-safe album management** (create, rename, delete, add/remove photos) persisted to `photosphere_albums.json` for both `ADMIN_EMAIL` and `ALLOWED_EMAILS`.
*   **Deliver full v2 functional parity (minus Quasar UX debt and dead stubs)** across Gallery & Lightbox (`/`), Unified Search & OSM Location Search, Memories (`/memories`), Writable Albums (`/albums`, `/albums/[albumName]`), and functional Settings (`/settings`).
*   **Fix existing v3 skeleton operational gaps** (`/api/readyz` auth exemption, middleware logging order, structured HTTP/cache/mutation telemetry, and automatic Firebase ID token refresh on `401`).

## Non-Goals

*   **Media database mutations from the web UI:** No photo/video uploads, deletions, or editing of labels, captions, or EXIF metadata in `ssr/`.
*   **External databases or search engines:** No Postgres, Firestore, or Elasticsearch; all data remains in contract-validated JSON files in GCS (`data_bucket`) and objects in `media_bucket`.
*   **Visual design token or styling specifications:** Color palettes, typography scales, spacing rules, and organism markup live exclusively in `./frontend-design-system.md`.
*   **Contract schema rewrites:** No breaking changes to `contracts/media_database.schema.json`, `contracts/albums.schema.json`, `contracts/kv_dictionary.schema.json`, or `contracts/photosphere_config.schema.json` (e.g., no adding image `width`/`height` or album UUIDs in this roadmap).
*   **Public or unauthenticated sharing:** Access stays restricted to Firebase-authenticated, email-verified accounts in `ALLOWED_EMAILS` / `ADMIN_EMAIL`.
*   **UI chrome localization:** `preferredLang` selects the GCS AI label/caption dictionary language only; UI labels and controls remain in English.

## Open Questions

*   **Legacy `GET /api/database` disposition:** Should `GET /api/database` be deleted once `/api/files` is live, or kept gated behind `assertAdminUser` as an admin diagnostic endpoint?

## Critical User Journeys (CUJs)

### CUJ 1: Mobile-First Gallery Browsing & Lightbox Viewing

*   **Given**: An allowlisted user signs in with Google on a mobile device (or desktop browser) and has an active Firebase session and scoped media session cookie.
*   **When**: The user opens `/`, scrolls through date-grouped photo and video tiles in the varied-row-span CSS Grid masonry, taps a photo or video, and navigates between adjacent items or opens the metadata drawer.
*   **Then**: Pages load incrementally via paginated `GET /api/files`, thumbnails load natively via `<img>` with browser and server disk caching (no `ARCHIVE` re-fetches on repeat views), tapping opens `MediaLightbox` directly with uncropped media and native video `Range` playback, and switching light/dark themes applies without a flash of the wrong theme.

### CUJ 2: Multi-Faceted Search & OSM Location Filtering

*   **Given**: An authenticated user is on `/` with a preferred AI dictionary language (`preferredLang`).
*   **When**: The user enters a search query (matching labels, captions, or filename), picks a date range or media type (`IMAGE` / `VIDEO`), or searches a place name via OpenStreetMap Nominatim with a radius filter.
*   **Then**: Filter state syncs to URL query parameters (preserving Back/Forward and reload), `/api/location/search` resolves places through a rate-limited, cached proxy without leaking errors as silent empty lists, and `GET /api/files` returns matching records using Haversine distance over non-null coordinates and language-aware label/caption indexes.

### CUJ 3: "On This Day" Memories

*   **Given**: An authenticated user has photos from prior years matching today's calendar month and day.
*   **When**: The user navigates to `/memories`.
*   **Then**: The server returns chronologically grouped media for the current `MM-DD` (excluding records with `created_at_timestamp: null`) in O(1) lookup time via the in-memory `byMonthDay` index, rendered with the same gallery grid and lightbox organisms as `/`.

### CUJ 4: Writable Album Management

*   **Given**: An allowlisted user (or admin) is authenticated and browsing `/` or `/albums`.
*   **When**: The user creates a new album, selects multiple photos in select mode to add or remove them from an album, renames an album, or deletes an album, and then opens `/albums/[albumName]` to browse it.
*   **Then**: The server validates the payload against `contracts/albums.schema.json`, serializes the write through a mutex, writes `photosphere_albums.json` to GCS with `ifGenerationMatch` optimistic concurrency (returning `409 Conflict` if stale), atomically updates local disk and in-memory caches only after GCS succeeds, and serves `/albums/[albumName]` via server-side paginated album filtering without passing hashes in URL query strings.

### CUJ 5: Settings, Theme/Language Preferences & Admin DB Refresh

*   **Given**: A signed-in user opens `/settings`.
*   **When**: The user toggles light/dark theme, changes `preferredLang`, or (if `isAdmin` via `GET /api/me`) triggers "Refresh Remote DB".
*   **Then**: Theme and language changes take effect immediately across views, non-admin users do not see admin-only refresh controls, and an admin refresh reloads `data_bucket` JSON files, rebuilds in-memory indexes, and displays updated record/album counts without stubbed or non-functional buttons.

--------------------------------------------------------------------------------

## Technical Plan (Architecture)

### System Architecture & Data Flows

```text
Browser (Nuxt 4 Client — Mobile-First Responsive)
  │
  ├─ JSON & Mutations (Authorization: Bearer <Firebase ID Token>)
  │   ├─ GET  /api/me                          -> Capabilities (email, isAdmin, canEditAlbums)
  │   ├─ POST /api/auth/session                -> Mint HttpOnly media session cookie
  │   ├─ GET  /api/files                       -> Paginated/filtered media (in-memory indexes)
  │   ├─ GET  /api/files/[hash]                -> Single record + localized labels & caption
  │   ├─ GET  /api/search/suggestions          -> Unified label + caption autocomplete
  │   ├─ GET  /api/location/search             -> Rate-limited, LRU-cached OSM Nominatim proxy
  │   ├─ GET/POST /api/albums                  -> List albums / create album (GCS write-through)
  │   ├─ GET/PATCH/DELETE /api/albums/[name]   -> Album detail / rename / edit hashes / delete
  │   └─ POST /api/admin/refresh-database      -> Admin-only reload of data_bucket + rebuild indexes
  │
  └─ Native <img> & <video> (HttpOnly Session Cookie — __ps_media)
      └─ GET /api/media/[hash]?variant=thumbnail|source
           │
           ├─ 1. Browser HTTP Cache (Cache-Control: private, max-age=31536000, immutable)
           ├─ 2. Server Bounded LRU Disk Cache (runtimeConfig.storage.mountedVolumePath/media)
           └─ 3. GCS media_bucket (ARCHIVE) via Server Credentials (only on cold cache miss)
```

### Shared Contracts & State Boundaries

All vertical slices below inherit these shared invariants:

1. **Standard Pagination & Error Envelope**
   * Every paginated list endpoint (`GET /api/files`, `GET /api/albums`) accepts `page` (default `1`, min `1`) and `limit` (default `50` for files / `20` for albums, max `100`) and returns `{ items, totalCount, page, limit, hasMore }`.
   * Every API error returns Nuxt/H3 JSON `{ statusCode, statusMessage, data?: { code, requestId } }` and echoes `x-request-id` in response headers so `usePhotosphereApi` can surface a correlation ID in logs and error banners.
2. **Dual Authentication Boundary**
   * **JSON & Mutation APIs (`/api/*` except `/api/healthz`, `/api/readyz`, `/api/media/*`):** Require `Authorization: Bearer <firebase_id_token>` with `email_verified === true` and membership in `ALLOWED_EMAILS` (`ADMIN_EMAIL` for admin routes). `usePhotosphereApi` automatically retries once after `user.getIdToken(true)` if an idle session hits `401`.
   * **Media Proxy (`GET /api/media/[hash]`):** Authenticates via an `HttpOnly; Secure; SameSite=Lax` Firebase Session Cookie (`__ps_media`, minted at login via `POST /api/auth/session` using `firebase-admin/auth` `createSessionCookie`, cleared on logout via `DELETE /api/auth/session`). Cookie verification checks signature and allowlist without calling `checkRevoked: true` on every thumbnail fetch. Mutating routes **never** accept the session cookie, preventing CSRF.
3. **Two-Bucket Storage, Indexing & Caching**
   * **`data_bucket` (`STANDARD`):** Loaded into memory and persisted under `runtimeConfig.storage.mountedVolumePath` (default `.photosphere-cache`, overridable via `PHOTOSPHERE_MOUNTED_VOLUME_PATH`). `file-database-cache.ts` remains strictly read-only and builds immutable derived indexes on load and on `POST /api/admin/refresh-database`:
     * `sortedHashes: string[]` (descending by `created_at_timestamp`, nulls last)
     * `byMonthDay: Map<string, string[]>` (`"MM-DD"` -> sorted hashes for O(1) Memories)
     * `byLabelIndex: Map<number, Set<string>>`
     * Per-language normalized lowercase lookup tables for labels and captions
   * **Writable Albums (`photosphere_albums.json`):** Managed through a serialized per-process async write mutex in `albums-cache.ts`. Every mutation validates against `contracts/albums.schema.json`, writes to GCS with `ifGenerationMatch` optimistic concurrency (returning `409 Conflict` if the remote generation changed), and only after GCS confirms does it call `writeFileAtomic` on disk and update the in-memory `albumsCache`. On GCS failure, local disk and memory remain unchanged.
   * **`media_bucket` (`ARCHIVE`):** Accessed only on disk-cache misses inside `GET /api/media/[hash]`. Cached under `<mountedVolumePath>/media/<hash>/<variant>` with an in-memory LRU metadata map (no per-write `fs.readdir` scans) and a configurable byte budget (`runtimeConfig.mediaCache.maxCacheBytes`, default 2 GB). Responses set `Cache-Control: private, max-age=31536000, immutable` and `ETag: "<hash>-<variant>"`. Video objects below `maxCacheableVideoBytes` (default 100 MB) are cached on first request and served with local HTTP `206 Partial Content` `Range` support; larger videos stream directly from GCS with `Range` pass-through.
4. **Permission Matrix**
   * `GET /api/me` returns `{ email: string, isAdmin: boolean, canEditAlbums: boolean }`.
   * Both `ADMIN_EMAIL` and `ALLOWED_EMAILS` receive `canEditAlbums: true` (enforced server-side and mirrored in GCS Firebase Storage rules path-locked to `photosphere_albums.json`).
   * Only `ADMIN_EMAIL` receives `isAdmin: true` (required for `POST /api/admin/refresh-database`).
5. **Presentational vs. Container & State Ownership**
   * Pages (`ssr/app/pages/*.vue`) act as thin containers: they read route query params (`useRoute`), call typed composables (`usePhotosphereApi`, `useMediaFeed`), and pass plain ViewModel props into data-agnostic organisms defined in `./frontend-design-system.md`.
   * **URL query params** own active search query, filters (`fileType`, `dateFrom`, `dateTo`, `lat`, `lng`, `radiusKm`, `place`), and active view state.
   * **Pinia** stays minimal: `useAuthStore` (session, `isAdmin`, `canEditAlbums`, `preferredLang`) and `useSelectionStore` (ephemeral multi-select hashes for bulk album operations).

---

### Phased Vertical Slice Roadmap

Every phase below uses the same structure (`Scope & Route`, `Nuxt API Contract`, `State & Caching`, `UI Organisms`, `Verification Criteria`) to keep slices independent and testable.

#### Phase 0: Platform Foundations & Operational Fixes

*   **Scope & Route:** Install Tailwind CSS v4, `shadcn-vue` (`reka-ui`), and `lucide-vue-next`; configure design tokens and FOUC-free light/dark theming per `./frontend-design-system.md`; fix v3 middleware order and `/api/readyz` exemption; add session cookie and capability endpoints; rebuild `/login` and `AppShell`; retire or admin-gate `GET /api/database`.
*   **Nuxt API Contract:**
    *   `GET /api/readyz` — exempt from `auth.ts` alongside `/api/healthz`.
    *   `00.request-logger.ts` — renamed so it executes before `auth.ts`; attaches response-finish hook emitting structured access logs (`method`, `path`, `statusCode`, `durationMs`, `userEmail`, `requestId`).
    *   `GET /api/me` — returns `{ email, isAdmin, canEditAlbums }`.
    *   `POST /api/auth/session` / `DELETE /api/auth/session` — exchanges verified Firebase ID token for `HttpOnly` `__ps_media` session cookie and clears it on sign-out.
*   **State & Caching:** Extend `useAuthStore` with `isAdmin` and `canEditAlbums`; add single-retry `401` token refresh (`getIdToken(true)`) and `x-request-id` capture in `usePhotosphereApi`; add `app/middleware/auth.global.ts` redirect guard and inline blocking theme script in `nuxt.config.ts`.
*   **UI Organisms (`./frontend-design-system.md`):** `AppShell` (mobile bottom nav + desktop left rail), `ThemeToggle`, `LoginCard`.
*   **Verification Criteria:** Unauthenticated `/api/readyz` returns `200`; `api_auth_denied` logs include `requestId`; sign-in mints `__ps_media` cookie and loads `/api/me`; light/dark toggle persists across hard reload with zero FOUC; `pnpm format && pnpm type-check && pnpm test && pnpm build` pass.

#### Phase 1: Media Proxy & Read-Only Gallery + Lightbox (`/`)

*   **Scope & Route:** Replace the raw JSON viewer at `/` with the date-grouped varied-row-span CSS Grid photo gallery and full-screen lightbox viewer with metadata drawer and download.
*   **Nuxt API Contract:**
    *   `GET /api/media/[hash]?variant=thumbnail|source` — cookie-authenticated media proxy backed by bounded LRU disk cache on `mountedVolumePath/media`, immutable browser cache headers, `Range` (`206`) video support, and null-thumbnail fallback (`IMAGE` falls back to `source_bucket_uri`; `VIDEO`/`FILE` return `404` or placeholder indicator handled by UI).
    *   `GET /api/files` — paginated list (`page`, `limit`) sorted newest-first using pre-sorted `sortedHashes`, returning lightweight ViewModels (`hash`, `fileType`, `createdAtTimestamp`, `thumbnailUrl`, `sourceUrl`, `hasThumbnail`).
    *   `GET /api/files/[hash]?lang=en` — full `MediaRecord` metadata plus resolved localized `labels: string[]` and `caption: string | null`.
*   **State & Caching:** `useMediaFeed` composable manages paginated pages, IntersectionObserver infinite scroll, and loading/error states; media URLs point directly to `/api/media/<hash>?variant=...` (zero JS blob URLs). Server emits `media_cache_hit`, `media_cache_miss`, `media_cache_eviction`, and `media_proxy_error` logs.
*   **UI Organisms (`./frontend-design-system.md`):** `MediaTimelineGrid` (v2 deterministic `nth-child(7n + k)` `span 1`/`span 2` CSS Grid grouped by date), `MediaTile`, `MediaLightbox` (swipe/keyboard nav, native `<video controls>`, collapsible metadata drawer, download button).
*   **Verification Criteria:** Gallery renders nullable `MediaRecord` fixtures (`created_at: null`, `thumbnail_bucket_uri: null`, `caption_index: null`) without errors; repeat thumbnail loads hit browser cache or server disk cache without GCS calls; `<video>` seeking returns `206 Partial Content`; mobile (375px) and desktop (1280px+) layouts pass in light and dark mode.

#### Phase 2: Unified Search, Suggestions & OSM Location Search

*   **Scope & Route:** Add search bar, filter sheet/popover, active filter chips, unified autocomplete suggestions, and OpenStreetMap Nominatim place search with radius filtering on `/`.
*   **Nuxt API Contract:**
    *   Extend `GET /api/files` with `q`, `lang`, `fileType` (`IMAGE | VIDEO | FILE`), `dateFrom`, `dateTo`, `lat`, `lng`, `radiusKm`. Location filter uses bounding-box pre-filter + Haversine distance over non-null `latitude`/`longitude` (explicitly excluding records with `null` coordinates).
    *   `GET /api/search/suggestions?q=...&lang=en&limit=10` — searches pre-normalized lowercase labels and captions in one call, returning tagged suggestions `{ text, kind: "label" | "caption" }`.
    *   `GET /api/location/search?q=...` — proxies OpenStreetMap Nominatim with server-side LRU cache, 1 req/sec rate limiter, `AbortSignal.timeout(5000)`, custom `User-Agent`, and structured `location_proxy_failed` error telemetry (returning `502`/`504` on upstream failure instead of silent `[]`).
*   **State & Caching:** Filter state lives in URL query parameters (`useRoute` / `navigateTo({ query })`) so reload and Back/Forward restore exact filtered results; client debounces search and location inputs (300ms / 500ms).
*   **UI Organisms (`./frontend-design-system.md`):** `SearchFilterBar`, `FilterSheet`, `LocationSearchPopover`, `ActiveFilterChips`, reusing `MediaTimelineGrid` and `MediaLightbox`.
*   **Verification Criteria:** Unit tests verify Haversine distance accuracy, exclusion of `null` coordinates, language fallback to `en`, Nominatim rate-limit/cache/timeout handling, and URL query round-tripping.

#### Phase 3: "On This Day" Memories (`/memories`)

*   **Scope & Route:** Implement `/memories` showing photos and videos taken on the current calendar month and day across prior years.
*   **Nuxt API Contract:**
    *   Extend `GET /api/files` with `memoryDate=MM-DD` (client-supplied local `MM-DD` so "today" matches the user's device timezone). Served in O(1) from the `byMonthDay` index in `file-database-cache.ts`, excluding records with `created_at_timestamp: null`.
*   **State & Caching:** Reuses `useMediaFeed({ memoryDate })` with zero new Pinia stores or dedicated Memories endpoints.
*   **UI Organisms (`./frontend-design-system.md`):** `PageHeader`, `MediaTimelineGrid`, `MediaLightbox`, `EmptyState`.
*   **Verification Criteria:** Records with `created_at_timestamp: null` never appear in memories; timezone boundary (`MM-DD` computed on client) matches expected photos; empty state renders cleanly when no prior-year media exists.

#### Phase 4: Writable Albums (`/albums`, `/albums/[albumName]`)

*   **Scope & Route:** Browse albums with server-derived cover previews, open an album's paginated media grid, and create, rename, delete, or add/remove photos from albums via multi-select mode.
*   **Nuxt API Contract:**
    *   `GET /api/albums?page=1&limit=20` — paginated album summaries `{ name, totalFiles, coverThumbnails: string[] }` (up to 4 valid hashes present in `media_database`, filtering out dangling hashes).
    *   `GET /api/files?album=<name>` and `GET /api/files?notInAlbum=true` — server-side `Set<string>` album intersection against `sortedHashes`, permanently eliminating v2's `hashList` / `excludeHashList` query-string bug.
    *   `POST /api/albums` — create `{ name, hashes?: string[] }`.
    *   `PATCH /api/albums/[albumName]` — rename (`{ newName }`) and/or mutate membership (`{ addHashes?, removeHashes? }`).
    *   `DELETE /api/albums/[albumName]` — remove album entry.
    *   Validation: reject empty names, `/`, control characters, and case-insensitive duplicates; validate all hashes are 40-char lowercase hex SHA-1 and conform to `contracts/albums.schema.json`.
*   **State & Caching:** Serialized write mutex + GCS `ifGenerationMatch` optimistic concurrency (`409 Conflict` on mismatch) + atomic disk/memory cache update only after GCS confirms; `album_mutated` audit logs (`actorEmail`, `action`, `albumName`, `hashCount`, `gcsGeneration`, `durationMs`). Client `useSelectionStore` holds ephemeral selected hashes for multi-select batch add/remove.
*   **UI Organisms (`./frontend-design-system.md`):** `AlbumGrid`, `AlbumCard`, `AlbumEditorDialog`, `AlbumPickerSheet`, `SelectionActionBar`, reusing `MediaTimelineGrid` and `MediaLightbox`.
*   **Verification Criteria:** Vitest tests cover album CRUD, invalid name rejection, case-insensitive uniqueness, `409 Conflict` handling, and rollback safety (GCS failure leaves local disk and `albumsCache` untouched); large albums (1,000+ photos) paginate cleanly via `?album=<name>`.

#### Phase 5: Settings & Admin Operations (`/settings`)

*   **Scope & Route:** Minimal, fully functional `/settings` page with zero stubbed controls (replacing v2's dead "Clear Cache" and "View Details" buttons).
*   **Nuxt API Contract:**
    *   Reuses `GET /api/me` and `POST /api/admin/refresh-database?lang=<lang>` (admin-only; reloads JSON files from `data_bucket`, rebuilds all in-memory derived indexes, and returns refreshed media and album counts).
*   **State & Caching:** Theme toggle (light/dark/system), `preferredLang` selector persisted in `useAuthStore` (reactive across search/lightbox), signed-in user email and sign-out action (calling `DELETE /api/auth/session` + Firebase `signOut`). Admin section renders only when `authStore.isAdmin === true`.
*   **UI Organisms (`./frontend-design-system.md`):** `SettingsSectionCard`, `ThemeToggle`, `LanguageSelector`, `AdminRefreshCard`.
*   **Verification Criteria:** Non-admin allowlisted user does not see DB refresh controls; admin refresh updates counts and invalidates stale indexes; sign-out clears both Firebase auth state and `__ps_media` cookie.

--------------------------------------------------------------------------------

## Alternatives Considered

### Alternative A: Client-Side `fetch()` + `URL.createObjectURL()` for Authenticated Media

*   **Pros**: Reuses the existing `Authorization: Bearer` middleware without adding a session cookie endpoint or server-side GCS media credentials.
*   **Cons**: Defeats browser HTTP disk caching across reloads, leaks mobile RAM under infinite scroll if blob URLs are not tracked and revoked aggressively, breaks native `<video>` HTTP `206 Partial Content` range seeking, and triggers dozens of Firebase Admin token-revocation RPCs per gallery page scroll.
*   **Reason for Rejection**: Rejected during technical review: breaks browser caching and video streaming while increasing mobile memory pressure and Firebase Auth RPC volume. Replaced with an `HttpOnly` Firebase Session Cookie scoped strictly to read-only `GET /api/media/[hash]`.

### Alternative B: Switching `media_bucket` from `ARCHIVE` to `STANDARD` GCS Storage Class

*   **Pros**: Eliminates GCS `ARCHIVE` retrieval fees (`$0.05/GB`) and higher Class B GET charges on cache misses.
*   **Cons**: Substantially increases recurring monthly storage costs for a large personal/family photo archive that is mostly cold data.
*   **Reason for Rejection**: Rejected by author: `ARCHIVE` storage class is required to keep long-term family photo storage costs low; retrieval costs are mitigated instead by immutable browser caching and a bounded persistent LRU disk cache under `runtimeConfig.storage.mountedVolumePath`.

### Alternative C: Client-Measured Justified-Row Masonry Grid

*   **Pros**: Preserves each photo's exact original aspect ratio directly inside the gallery grid like native Google Photos.
*   **Cons**: `contracts/media_database.schema.json` does not store `width` or `height` (and sets `additionalProperties: false`). Measuring natural image dimensions on the client causes severe Cumulative Layout Shift (CLS) while scrolling on mobile.
*   **Reason for Rejection**: Rejected during technical review: avoided schema churn and mobile CLS by adopting v2's deterministic CSS Grid varied-row-span masonry (`grid-auto-rows` + `nth-child(7n + k)` `span 1`/`span 2` + `object-fit: cover`) with uncropped viewing in `MediaLightbox`.

### Alternative D: Porting v2's `hashList` / `excludeHashList` Query Params and Precision-5 Geohash Filter

*   **Pros**: Direct copy of v2's `GET /api/files` filtering logic.
*   **Cons**: Passing album hashes in GET query strings hits URL length limits on large albums; v2's precision-5 geohash (~5 km box) ignored the radius parameter, failed across cell boundaries, and falsely matched records with `geohash: null`.
*   **Reason for Rejection**: Rejected during technical review: replaced with server-side `Set<string>` album filtering (`?album=` / `?notInAlbum=true`) and bounding-box + Haversine distance over non-null `latitude`/`longitude`.

### Alternative E: Single Monolithic Design Document

*   **Pros**: One file to read for both visual design rules and API/feature rollout.
*   **Cons**: Mixes timeless frontend styling conventions with sequential implementation slices, causing dual-purpose bloat and making it harder for a backend-oriented developer to reference UI rules independently on future features.
*   **Reason for Rejection**: Rejected by author: requested two separate documents in `docs/` (`docs/designs/frontend-design-system.md` and `docs/designs/recreation-roadmap.md`) with a strict ownership boundary.

--------------------------------------------------------------------------------

## Non-Functional Requirements

*   **Security & Privacy**:
    *   Every `/api/*` route except `/api/healthz` and `/api/readyz` requires verified authentication and case-insensitive membership in `ALLOWED_EMAILS` / `ADMIN_EMAIL`.
    *   Mutating routes (`POST`, `PATCH`, `DELETE`) accept only `Authorization: Bearer <firebase_id_token>` (never the `__ps_media` cookie), preventing CSRF.
    *   Media requests address objects by SHA-1 `hash` and `variant` (`thumbnail | source`), never raw GCS paths, preventing path traversal.
    *   GCS Firebase Storage rules on `data_bucket` remain read-only for `photosphere_database_cloud.json` and language dictionaries, allowing writes strictly to `photosphere_albums.json`.
*   **Performance, Latency & Cost Economics**:
    *   `GET /api/files`, `GET /api/albums`, `GET /api/search/suggestions`, and `/memories` operate purely on pre-sorted/pre-indexed in-memory data structures (sub-millisecond filtering without full-array re-sorting per request).
    *   `GET /api/media/[hash]` sets `Cache-Control: private, max-age=31536000, immutable` and uses an in-memory LRU index over `<mountedVolumePath>/media` (no O(N) `fs.readdir` eviction on writes) to minimize `ARCHIVE` GCS retrievals.
    *   `/api/location/search` enforces a 1 req/sec Nominatim rate limit, LRU cache, and 5-second timeout to prevent IP bans and hanging requests.
*   **Observability & Debuggability**:
    *   `00.request-logger.ts` runs before `auth.ts` so every API request (including auth denials) carries `requestId` and `traceContext` and emits structured completion logs (`method`, `path`, `statusCode`, `durationMs`, `userEmail`).
    *   Dedicated structured Pino events track `media_cache_hit`, `media_cache_miss`, `media_cache_eviction`, `media_proxy_error`, `album_mutated`, and `location_proxy_failed`.
    *   `usePhotosphereApi` captures `x-request-id` on errors for frontend-to-backend correlation.
*   **Rollout & Rollback**:
    *   Each phase (0 through 5) ships independently with passing `pnpm format && pnpm type-check && pnpm test && pnpm build`.
    *   Album writes apply to GCS first with `ifGenerationMatch`; any GCS error leaves local disk and `albumsCache` unmodified (automatic rollback).

--------------------------------------------------------------------------------

### Additional Resources

*   Companion Frontend Design System: `./frontend-design-system.md` (owns design tokens, light/dark CSS variables, typography/spacing scales, `shadcn-vue` setup, and data-agnostic organism interfaces).
*   Predecessor Ideation Brief: `../../concepts_brief.md`
*   v3 Data Contracts: `../../contracts/media_database.schema.json`, `../../contracts/albums.schema.json`, `../../contracts/kv_dictionary.schema.json`, `../../contracts/photosphere_config.schema.json`
*   v2 Reference Implementation: `../../../photosphere-v2/ssr`

--------------------------------------------------------------------------------

## Detailed Implementation Plan

All files below are ordered by implementation phase (Phase 0 through Phase 5) in one unified list. Visual/token styling details and internal organism markup follow `./frontend-design-system.md`.

### Target Files to Create, Modify, or Delete

#### Phase 0 — Platform Foundations, Middleware Fixes & Auth Session

1.  **`ssr/package.json`** (Modify)
    *   **Type / Scope**: Package Manifest
    *   **Proposed Changes**: Add Tailwind CSS v4 (`tailwindcss`, `@tailwindcss/vite`), `shadcn-vue` runtime dependencies (`reka-ui`, `class-variance-authority`, `clsx`, `tailwind-merge`), and `lucide-vue-next` so the design system and organism components can be built without Quasar.
2.  **`ssr/nuxt.config.ts`** (Modify)
    *   **Type / Scope**: Nuxt Configuration
    *   **Proposed Changes**: Register the Tailwind v4 Vite plugin, add `runtimeConfig.mediaCache` (`maxCacheBytes`, `maxCacheableVideoBytes`, `directoryName`), add `runtimeConfig.location` (Nominatim base URL, rate-limit interval, timeout, user-agent), and inject an inline blocking `<head>` theme script to apply `.dark` before first paint (preventing SSR theme FOUC).
3.  **`ssr/components.json`** (Create)
    *   **Type / Scope**: `shadcn-vue` Configuration
    *   **Proposed Changes**: Configure `shadcn-vue` CLI aliases pointing to `app/components/ui`, `app/assets/main.css`, and `app/lib/utils.ts` per Nuxt 4 `app/` directory conventions.
4.  **`ssr/server/middleware/00.request-logger.ts`** (Create) & **`ssr/server/middleware/request-logger.ts`** (Delete)
    *   **Type / Scope**: Nitro Server Middleware
    *   **Proposed Changes**: Rename `request-logger.ts` to `00.request-logger.ts` so Nitro executes it alphabetically before `auth.ts` (preserving `requestId` and `traceContext` on `api_auth_denied` logs), and attach a response-finish hook emitting structured HTTP completion logs (`method`, `path`, `statusCode`, `durationMs`, `userEmail`).
5.  **`ssr/server/middleware/auth.ts`** (Modify)
    *   **Type / Scope**: Nitro Server Middleware
    *   **Proposed Changes**: Exempt `/api/readyz` alongside `/api/healthz`; route `/api/media/*` `GET` requests to Firebase Session Cookie verification (`__ps_media`) without calling `checkRevoked: true` per thumbnail, while strictly requiring `Authorization: Bearer <firebase_id_token>` for all other `/api/*` JSON and mutating routes.
6.  **`ssr/server/services/auth.service.ts`** (Modify)
    *   **Type / Scope**: Server Auth Service
    *   **Proposed Changes**: Add `createMediaSessionCookie(idToken)` and `verifyMediaSessionCookie(cookie)` helpers using `firebase-admin/auth`, verifying allowlist membership and returning the authorized user context.
7.  **`ssr/server/api/auth/session.post.ts`** (Create) & **`ssr/server/api/auth/session.delete.ts`** (Create)
    *   **Type / Scope**: Nuxt Server API
    *   **Proposed Changes**: `POST` exchanges a verified Firebase ID token for an `HttpOnly; Secure; SameSite=Lax` `__ps_media` cookie (`Path=/api/media`); `DELETE` clears the cookie on sign-out.
8.  **`ssr/server/api/me.get.ts`** (Create)
    *   **Type / Scope**: Nuxt Server API
    *   **Proposed Changes**: Return `{ email, isAdmin, canEditAlbums }` derived from `auth.service.ts` so the client UI can gate admin-only controls cleanly without exposing `ADMIN_EMAIL`.
9.  **`ssr/server/api/database/index.get.ts`** (Modify or Delete — per Open Question)
    *   **Type / Scope**: Legacy Nuxt Server API
    *   **Proposed Changes**: Gate behind `assertAdminUser` for admin diagnostics (or delete once Phase 1 `/api/files` is verified) so unpaginated multi-MB JSON dumps are not exposed to standard browsing.
10. **`ssr/app/stores/auth.ts`** (Modify)
    *   **Type / Scope**: Pinia Store
    *   **Proposed Changes**: Add `isAdmin` and `canEditAlbums` reactive state populated from `GET /api/me` after sign-in, and reset them on logout.
11. **`ssr/app/composables/useFirebaseAuth.ts`** (Modify)
    *   **Type / Scope**: Vue Composable
    *   **Proposed Changes**: Call `POST /api/auth/session` and `GET /api/me` on sign-in / auth restoration, and call `DELETE /api/auth/session` on logout before signing out of Firebase.
12. **`ssr/app/composables/usePhotosphereApi.ts`** (Modify)
    *   **Type / Scope**: Vue Composable
    *   **Proposed Changes**: Add single-retry `401` token refresh (`currentUser.getIdToken(true)`), capture `x-request-id` headers on errors for debugging correlation, and add typed methods for `/api/me`, `/api/files`, `/api/files/[hash]`, `/api/search/suggestions`, `/api/location/search`, and `/api/albums` CRUD.
13. **`ssr/app/layouts/default.vue`** (Modify) & **`ssr/app/pages/login.vue`** (Modify)
    *   **Type / Scope**: Nuxt Layout & Login Page
    *   **Proposed Changes**: Replace the skeleton topbar/card markup with `AppShell` (mobile bottom navigation + desktop rail) and `LoginCard` from `./frontend-design-system.md`.

#### Phase 1 — Media Proxy, Derived Indexes & Read-Only Gallery + Lightbox (`/`)

14. **`ssr/server/utils/file-database-cache.ts`** (Modify)
    *   **Type / Scope**: Server Data Cache & Indexer
    *   **Proposed Changes**: Keep strictly read-only; extend the loaded cache snapshot with immutable derived indexes rebuilt on load and refresh: `byMonthDay: Map<string, string[]>`, `byLabelIndex: Map<number, Set<string>>`, and per-language pre-normalized lowercase label/caption search tables.
15. **`ssr/server/services/media-cache.service.ts`** (Create)
    *   **Type / Scope**: Server Media Cache Service
    *   **Proposed Changes**: Implement bounded persistent LRU disk cache under `<runtimeConfig.storage.mountedVolumePath>/media/<hash>/<variant>` with an in-memory LRU index (avoiding per-write `fs.readdir`), GCS `mediaBucket` fetch on cold miss, local HTTP `206 Partial Content` `Range` serving for cached videos (and Range pass-through for videos exceeding `maxCacheableVideoBytes`), `Cache-Control: private, max-age=31536000, immutable`, `ETag`, and structured Pino logs (`media_cache_hit`, `media_cache_miss`, `media_cache_eviction`, `media_proxy_error`).
16. **`ssr/server/api/media/[hash].get.ts`** (Create)
    *   **Type / Scope**: Nuxt Server API
    *   **Proposed Changes**: Validate 40-char SHA-1 `hash` and `variant` (`thumbnail | source`), resolve `thumbnail_bucket_uri` or `source_bucket_uri` from `file-database-cache.ts` (falling back to `source_bucket_uri` when `file_type === "IMAGE"` and `thumbnail_bucket_uri === null`), and stream through `media-cache.service.ts`.
17. **`ssr/server/utils/file-filters.ts`** (Create)
    *   **Type / Scope**: Server Query & Filter Utility
    *   **Proposed Changes**: Pure functions matching `MediaRecord` against `fileType`, `dateFrom`/`dateTo`, `q` (labels, captions, filename), `memoryDate` (`MM-DD`), `album` / `notInAlbum` (`Set<string>`), and bounding-box + Haversine distance over non-null `latitude`/`longitude`.
18. **`ssr/server/api/files/index.get.ts`** (Create) & **`ssr/server/api/files/[hash].get.ts`** (Create)
    *   **Type / Scope**: Nuxt Server API
    *   **Proposed Changes**: `index.get.ts` returns paginated `{ items, totalCount, page, limit, hasMore }` ViewModels using pre-sorted `sortedHashes` and `file-filters.ts`; `[hash].get.ts` returns full `MediaRecord` detail plus localized `labels` and `caption`.
19. **`ssr/app/types/api/index.ts`** (Modify) & **`ssr/app/types/media.ts`** (Create)
    *   **Type / Scope**: Client TypeScript Types
    *   **Proposed Changes**: Define typed ViewModels and API envelopes (`PaginatedResponse<T>`, `MediaGridItem`, `MediaDetail`, `AlbumSummary`, `LocationResult`, `UserCapabilities`) matching `contracts/` snake_case-to-ViewModel mapping.
20. **`ssr/app/composables/useMediaFeed.ts`** (Create)
    *   **Type / Scope**: Vue Composable
    *   **Proposed Changes**: Reusable paginated media feed loader with IntersectionObserver trigger, active lightbox item navigation (prev/next across loaded pages), and error/loading state shared by `/`, `/memories`, and `/albums/[albumName]`.
21. **`ssr/app/pages/index.vue`** (Modify)
    *   **Type / Scope**: Nuxt Page Container
    *   **Proposed Changes**: Replace the raw JSON viewer with a thin page container binding URL query params and `useMediaFeed` to `SearchFilterBar`, `MediaTimelineGrid`, `SelectionActionBar`, and `MediaLightbox`.

#### Phase 2 — Unified Search, Suggestions & OSM Location Search

22. **`ssr/server/api/search/suggestions.get.ts`** (Create)
    *   **Type / Scope**: Nuxt Server API
    *   **Proposed Changes**: Query pre-normalized lowercase label and caption tables for the requested `lang` (with `en` fallback) in one call, returning top `limit` deduplicated `{ text, kind: "label" | "caption" }` items.
23. **`ssr/server/services/location-proxy.service.ts`** (Create) & **`ssr/server/api/location/search.get.ts`** (Create)
    *   **Type / Scope**: Server Location Proxy & API
    *   **Proposed Changes**: Proxy OpenStreetMap Nominatim with an in-memory LRU cache, 1 req/sec rate limiter, `AbortSignal.timeout(5000)`, custom `User-Agent`, and `location_proxy_failed` Pino telemetry (returning `502`/`504` on upstream errors rather than silent `[]`).
24. **`ssr/app/composables/useGalleryFilters.ts`** (Create)
    *   **Type / Scope**: Vue Composable
    *   **Proposed Changes**: Two-way sync between gallery search/filter state (`q`, `fileType`, `dateFrom`, `dateTo`, `lat`, `lng`, `radiusKm`, `place`) and `useRoute().query` with debounced URL updates.

#### Phase 3 — "On This Day" Memories (`/memories`)

25. **`ssr/app/pages/memories.vue`** (Create)
    *   **Type / Scope**: Nuxt Page Container
    *   **Proposed Changes**: Compute local device `MM-DD`, pass `memoryDate` into `useMediaFeed`, and render `PageHeader`, `MediaTimelineGrid`, `MediaLightbox`, and `EmptyState`.

#### Phase 4 — Writable Albums (`/albums`, `/albums/[albumName]`)

26. **`ssr/server/utils/storage-upload.ts`** (Create)
    *   **Type / Scope**: Server GCS Write Utility
    *   **Proposed Changes**: Implement GCS upload for `photosphere_albums.json` using GCS JSON API / Firebase Storage with object `generation` tracking and `ifGenerationMatch` optimistic concurrency precondition, translating precondition failures (`412`) into typed `409 Conflict` errors.
27. **`ssr/server/utils/albums-cache.ts`** (Modify)
    *   **Type / Scope**: Server Album Repository & Cache
    *   **Proposed Changes**: Track remote GCS `generation`, add a per-process async write mutex, enforce album name validation (non-empty, no `/` or control chars, case-insensitive uniqueness), validate payloads against `contracts/albums.schema.json`, execute GCS-first write-through -> `writeFileAtomic` -> in-memory cache update, and emit `album_mutated` audit logs.
28. **`ssr/server/api/albums/index.get.ts`** (Create), **`ssr/server/api/albums/index.post.ts`** (Create), **`ssr/server/api/albums/[albumName].get.ts`** (Create), **`ssr/server/api/albums/[albumName].patch.ts`** (Create), **`ssr/server/api/albums/[albumName].delete.ts`** (Create)
    *   **Type / Scope**: Nuxt Server API
    *   **Proposed Changes**: Paginated album listing with server-derived cover hashes (filtering out dangling hashes), album creation, single-album metadata retrieval, rename + `addHashes`/`removeHashes` patching, and album deletion.
29. **`ssr/app/stores/selection.ts`** (Create)
    *   **Type / Scope**: Pinia Store
    *   **Proposed Changes**: Hold ephemeral multi-select mode (`active: boolean`, `selectedHashes: Set<string>`) for batch adding/removing photos to/from albums across `/` and `/albums/[albumName]`.
30. **`ssr/app/pages/albums/index.vue`** (Create) & **`ssr/app/pages/albums/[albumName].vue`** (Create)
    *   **Type / Scope**: Nuxt Page Containers
    *   **Proposed Changes**: `/albums` renders `AlbumGrid` and `AlbumEditorDialog` (create/rename/delete); `/albums/[albumName]` passes `album` into `useMediaFeed` and renders `MediaTimelineGrid`, `SelectionActionBar` (remove from album), and `MediaLightbox`.

#### Phase 5 — Settings & Admin Operations (`/settings`)

31. **`ssr/app/pages/settings.vue`** (Create)
    *   **Type / Scope**: Nuxt Page Container
    *   **Proposed Changes**: Wire `ThemeToggle`, `LanguageSelector` (`useAuthStore.preferredLang`), signed-in account info + logout, and `isAdmin`-gated `AdminRefreshCard` calling `POST /api/admin/refresh-database`.

#### Verification & Test Files

32. **`ssr/test/server/auth.test.ts`** (Modify)
    *   **Type / Scope**: Vitest Unit Test
    *   **Proposed Changes**: Add assertions for `/api/readyz` auth exemption, `00.request-logger.ts` `requestId` propagation on `401`/`403`, `__ps_media` session cookie verification on `/api/media/*`, and rejection of cookies on mutating routes.
33. **`ssr/test/server/files-and-filters.test.ts`** (Create)
    *   **Type / Scope**: Vitest Unit Test
    *   **Proposed Changes**: Test `GET /api/files`, `GET /api/files/[hash]`, `GET /api/search/suggestions`, nullable `MediaRecord` fixtures (`contracts/fixtures/`), `byMonthDay` Memories lookup, Haversine distance filtering (excluding `null` coords), and server-side `?album=` / `?notInAlbum=true` filtering.
34. **`ssr/test/server/media-proxy.test.ts`** (Create)
    *   **Type / Scope**: Vitest Unit Test
    *   **Proposed Changes**: Test `GET /api/media/[hash]` disk cache hit/miss, bounded LRU eviction, `Cache-Control: immutable` + `ETag`, `206 Partial Content` `Range` responses, and `thumbnail_bucket_uri: null` fallback.
35. **`ssr/test/server/albums-crud.test.ts`** (Create)
    *   **Type / Scope**: Vitest Unit Test
    *   **Proposed Changes**: Test album create/rename/add/remove/delete, invalid name rejection, case-insensitive duplicate rejection, `409 Conflict` on `ifGenerationMatch` mismatch, and rollback safety confirming GCS write failures leave local disk and memory caches unchanged.
36. **`ssr/test/server/location-search.test.ts`** (Create)
    *   **Type / Scope**: Vitest Unit Test
    *   **Proposed Changes**: Test Nominatim LRU caching, 1 req/sec rate limiting, timeout handling, and `502`/`504` error responses.
37. **`ssr/test/server/database-endpoint.test.ts`** (Modify or Delete)
    *   **Type / Scope**: Vitest Unit Test
    *   **Proposed Changes**: Update to verify admin-only gating on `GET /api/database` (or delete alongside `ssr/server/api/database/index.get.ts` if retired).
38. **`ssr/README.md`** (Modify)
    *   **Type / Scope**: Package Documentation
    *   **Proposed Changes**: Update architecture summary, endpoint table, and environment/cache notes to match the recreated v3 webapp.

### Verification Plan

*   **Formatting & Static Analysis**: `pnpm --dir ssr format && pnpm --dir ssr type-check`
*   **Unit & API Tests**: `pnpm --dir ssr test` (all existing and new Vitest server suites green at every phase, using `contracts/fixtures/` for nullable field coverage)
*   **Production Build**: `pnpm --dir ssr build`
*   **Manual / Responsive Verification per Phase**:
    *   Verify mobile viewport (`375x812`) and desktop viewport (`1440x900`) in both Light and Dark themes with hard reload (zero FOUC).
    *   Verify browser Network tab on repeat gallery scroll confirms `Cache-Control: immutable` hits and zero repeat GCS `ARCHIVE` calls; verify `<video>` scrubbing returns `206 Partial Content`.
    *   Verify non-admin allowlisted account can create/edit/delete albums and cannot see or invoke `POST /api/admin/refresh-database`.

--------------------------------------------------------------------------------

*Drafted with EGM*
