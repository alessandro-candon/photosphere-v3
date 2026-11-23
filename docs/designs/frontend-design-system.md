# Photosphere v3 SSR — Frontend Design System & Organism Component Architecture

* **Author:** alessandro-candon
* **Status:** Proposed
* **Date:** 2026-11-22

--------------------------------------------------------------------------------

## 1. Purpose & Document Boundary

This document is the single source of truth for Photosphere v3 visual design, layout conventions, and component architecture inside `ssr/app/`. Every new page or feature must reuse the tokens, primitives, molecules, and organisms defined here instead of inventing ad-hoc CSS, colors, or wrapper components.

* **What this document owns:** Stack setup (`Nuxt 4`, `Tailwind CSS v4`, `shadcn-vue`, `lucide-vue-next`), light/dark semantic CSS tokens, FOUC-free theme loading, typography, spacing, touch-target minimums, responsive navigation, deterministic CSS Grid masonry layout, and data-agnostic component interfaces across the 3-tier hierarchy.
* **What this document does NOT own:** Nuxt server API contracts, GCS storage/caching mechanics, Pinia store internals, and URL query contracts. Those live in the companion Feature-by-Feature Recreation Roadmap (`./recreation-roadmap.md`).

---

## 2. Frontend Stack & Configuration Contract

Photosphere v3 uses a fixed frontend stack inside `ssr/`:

* **Framework:** Nuxt 4 (`ssr/app/` source root, `ssr/app/pages/`, `ssr/app/components/`) + Vue 3.5+ (`<script setup lang="ts">`).
* **Styling:** Tailwind CSS v4 via `@tailwindcss/vite`, imported in `ssr/app/assets/main.css` with `@import "tailwindcss";` and class-based dark mode `@custom-variant dark (&:where(.dark, .dark *));`.
* **UI Primitives:** `shadcn-vue` (`reka-ui`, `class-variance-authority`, `clsx`, `tailwind-merge`) configured in `ssr/components.json` pointing to `app/components/ui`, `app/assets/main.css`, and `app/lib/utils.ts` (`cn()` helper).
* **Icons:** `lucide-vue-next` exclusively (no raw inline SVG icons except brand marks if needed).

### Anti-FOUC Theme Initialization

Because Nuxt SSR renders HTML before reading browser `localStorage`, an inline blocking `<script>` in `ssr/nuxt.config.ts` (`app.head.script`) runs before first paint:

```js
(function () {
  try {
    var stored = localStorage.getItem('photosphere_theme');
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    var isDark = stored ? stored === 'dark' : prefersDark;
    if (isDark) document.documentElement.classList.add('dark');
    else document.documentElement.classList.remove('dark');
  } catch (e) {}
})();
```

---

## 3. Semantic Color Tokens (Light & Dark)

**Hard Rule:** Feature components and organisms MUST NOT use raw hex values or Tailwind palette colors (`bg-slate-900`, `text-gray-500`, `dark:bg-zinc-800`). Use semantic token classes (`bg-background`, `bg-surface`, `bg-surface-elevated`, `text-foreground`, `text-muted-foreground`, `bg-primary`, `text-primary-foreground`, `bg-destructive`, `border-border`) so light and dark themes switch at `:root` / `.dark` in one place.

Defined in `ssr/app/assets/main.css` and mapped through Tailwind v4 `@theme inline`:

| Semantic Token | Light (`:root`) | Dark (`.dark`) | Usage |
| :--- | :--- | :--- | :--- |
| `--background` | `#ffffff` | `#0b0f17` | Main viewport canvas |
| `--surface` | `#f8fafc` | `#121826` | Cards, nav rail, bottom bar, header |
| `--surface-elevated` | `#ffffff` | `#1b2333` | Dialogs, sheets, dropdowns, popovers |
| `--foreground` | `#0f172a` | `#f1f5f9` | Primary headings and body copy |
| `--muted` | `#f1f5f9` | `#1e293b` | Subtle container fills, inactive chips, tile skeletons |
| `--muted-foreground` | `#475569` | `#94a3b8` | Secondary captions, timestamps, labels |
| `--primary` | `#1a73e8` | `#60a5fa` | Primary CTAs, active nav, selection rings |
| `--primary-foreground` | `#ffffff` | `#091324` | Text/icons on `--primary` |
| `--destructive` | `#dc2626` | `#ef4444` | Delete album, error banners, destructive actions |
| `--destructive-foreground` | `#ffffff` | `#ffffff` | Text/icons on `--destructive` |
| `--border` | `#e2e8f0` | `#263248` | Dividers, card hairlines, inputs |
| `--ring` | `#1a73e8` | `#60a5fa` | Focus-visible outlines |
| `--scrim` | `rgba(15, 23, 42, 0.72)` | `rgba(3, 7, 18, 0.85)` | Lightbox backdrop and overlay controls |

---

## 4. Typography, Spacing & Touch Ergonomics

### Font Families

* **Sans (`--font-sans`):** `Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif`
* **Mono (`--font-mono`):** `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace`

### Type Scale

| Role | Tailwind Classes | Typical Use |
| :--- | :--- | :--- |
| **Page Title** | `text-xl sm:text-2xl font-semibold tracking-tight` | View headers (`Photos`, `Memories`, `Albums`, `Settings`) |
| **Section / Date Header** | `text-sm sm:text-base font-semibold tracking-tight` | Sticky/grouped gallery date headers |
| **Card Title** | `text-base font-medium` | Album names, settings group titles, dialog titles |
| **Body** | `text-sm leading-relaxed` | Descriptions, captions, form controls |
| **Caption / Metadata** | `text-xs text-muted-foreground` | Counts, timestamps, chip labels |
| **Mono ID / Hash** | `font-mono text-xs text-muted-foreground` | SHA-1 digests, request correlation IDs, coordinates |

### Spacing, Radii & Mobile Touch Targets

* **Minimum Interactive Target:** Every tappable button, icon button, nav link, and tile checkbox on mobile MUST satisfy `min-h-11 min-w-11` (`44px x 44px`) or expand its hit area accordingly.
* **Shell Padding:** Mobile `px-3 py-3` with bottom bar clearance (`pb-20 md:pb-6`); desktop `md:px-6 md:py-5` with left rail clearance (`md:pl-20 lg:pl-60`).
* **Radii:** Tiles (`rounded-sm` / `4px`), inputs & buttons (`rounded-lg` / `8px`), cards & dialogs (`rounded-xl` / `12px`), pills & chips (`rounded-full`).

---

## 5. Responsive Layout & Deterministic Gallery Masonry

### Navigation Chrome (`AppShell`)

* **Mobile (`< 768px`, `< md`):**
  * Compact sticky top bar (`h-14`) for page brand/search trigger + theme/account action.
  * Fixed bottom navigation bar (`h-16`) with 4 primary destinations: **Photos** (`/`), **Memories** (`/memories`), **Albums** (`/albums`), **Settings** (`/settings`).
* **Desktop (`>= 768px`, `md:`+):**
  * Persistent left navigation rail (`w-16 md:w-20 lg:w-56`) replacing the bottom bar, plus clean top utility bar inside the main column (`max-w-[1600px] mx-auto`).

### Zero-CLS Deterministic CSS Grid Masonry (Google Photos Rhythm)

Because `contracts/media_database.schema.json` does not store image pixel `width`/`height`, measuring image aspect ratios on the client would cause severe Cumulative Layout Shift (CLS) on mobile scroll. Instead, Photosphere v3 uses the deterministic CSS Grid varied-row-span pattern proven in v2:

* **Date-Grouped Sections:** Media items are grouped into sections under chronological date headers (`e.g. Fri, Aug 15, 2024`).
* **CSS Grid Geometry (`.ps-masonry-grid`):**
  * Mobile (`< 640px`): `grid-template-columns: repeat(2, minmax(0, 1fr))` (or 3 columns on compact mode), `gap: 3px`, `grid-auto-rows: 120px`, `grid-auto-flow: dense`.
  * Tablet (`640px–1023px`): `grid-template-columns: repeat(auto-fill, minmax(180px, 1fr))`, `gap: 4px`, `grid-auto-rows: 135px`.
  * Desktop (`>= 1024px`): `grid-template-columns: repeat(auto-fill, minmax(220px, 1fr))`, `gap: 6px`, `grid-auto-rows: 145px`.
* **Varied Row Spans (`.ps-masonry-item`):**
  * Items cycle deterministically (`nth-child(7n + 2)`, `nth-child(7n + 4)`, `nth-child(7n + 6)` span 2 rows: `grid-row-end: span 2`; others span 1 row).
  * Thumbnails fill their tile via `w-full h-full object-cover`.
  * Clicking a tile opens `MediaLightbox` directly with **uncropped** full-aspect rendering (`object-contain`).

---

## 6. Three-Tier Component Architecture & Directory Map

All Vue components live under `ssr/app/components/` and follow a strict dependency direction (`pages/` -> `organisms/` -> `common/` -> `ui/`):

```text
ssr/app/
  lib/utils.ts                    # cn() class-merging utility
  components/
    ui/                           # Tier 1: Untouched shadcn-vue primitives
    common/                       # Tier 2: Thin reusable app molecules
    organisms/                    # Tier 3: Data-agnostic domain blocks
  pages/                          # Thin route containers (Pinia + URL + API wiring)
```

### Tier 1: `app/components/ui/` (Untouched `shadcn-vue` Primitives)

* Contains only `shadcn-vue` primitives (`Button`, `Input`, `Badge`, `Skeleton`, `Card`, `Dialog`, `Sheet`, `Select`).
* **Rule:** Never add Photosphere domain logic, API calls, or store imports inside `components/ui/`. Keep primitives clean so upstream `shadcn-vue` updates stay frictionless.

### Tier 2: `app/components/common/` (App Molecules)

Reusable building blocks composed from `ui/` and `lucide-vue-next`, accepting primitive props only:

| Component | Purpose | Key Props / Emits |
| :--- | :--- | :--- |
| `ThemeToggle.vue` | Light/Dark theme switch | `theme: 'light' \| 'dark'` / `@toggle` |
| `LanguageSelector.vue` | AI label/caption language picker | `modelValue: string`, `options: Array<{code, label}>` / `@update:modelValue` |
| `MediaTile.vue` | Single gallery tile with lazy `<img>`, video/file badge, null-thumbnail fallback, and selection checkbox | `item: MediaTileViewModel`, `selected: boolean`, `selecting: boolean` / `@open`, `@toggle-select` |
| `EmptyState.vue` | Consistent zero-results / empty album / no-memories state | `icon`, `title`, `description` + default CTA slot |
| `ErrorBanner.vue` | Inline error alert with optional retry and request-id copy/display | `message: string`, `requestId?: string` / `@retry` |
| `ConfirmDialog.vue` | Confirmation modal for destructive actions (e.g., delete album) | `open`, `title`, `description`, `confirmLabel`, `destructive` / `@confirm`, `@cancel` |

### Tier 3: `app/components/organisms/` (Domain Compositions)

Data-agnostic presentational blocks. They accept plain typed ViewModels as props, emit semantic user-intent events, and **never** call `fetch()` or import Pinia stores directly (route pages in `app/pages/` wire composables and Pinia stores into organisms):

| Organism | Role | Key Props / Slots / Emits |
| :--- | :--- | :--- |
| `AppShell.vue` | Responsive navigation frame (mobile bottom nav + desktop left rail + top header bar) | `userEmail`, `currentPath`, `theme` + header-actions slot / `@logout`, `@toggle-theme` |
| `LoginCard.vue` | Centered Google sign-in card | `loading`, `error` / `@sign-in` |
| `PageHeader.vue` | Standardized page heading bar with optional back link, subtitle badge, and action buttons | `title`, `subtitle?`, `backTo?` + actions slot |
| `SearchFilterBar.vue` | Search input with suggestions dropdown, active filter chips, and filter sheet trigger | `query`, `suggestions`, `filters`, `locationResults`, `locationLoading`, `locationError` / `@update:query`, `@select-suggestion`, `@search-location`, `@apply-filters`, `@clear-filters` |
| `MediaTimelineGrid.vue` | Date-grouped `.ps-masonry-grid` with skeleton loading state, IntersectionObserver infinite scroll trigger, and selection mode toggle | `items`, `loading`, `loadingMore`, `hasMore`, `selecting`, `selectedHashes` / `@open-item`, `@toggle-select`, `@load-more` |
| `MediaLightbox.vue` | Full-screen photo/video viewer with keyboard/button prev-next navigation, native `<video controls>`, collapsible EXIF/AI metadata drawer, download, and "Add to album" trigger | `open`, `item`, `detail`, `detailLoading`, `hasPrev`, `hasNext`, `canEditAlbums` / `@close`, `@prev`, `@next`, `@add-to-album`, `@download` |
| `SelectionActionBar.vue` | Sticky bottom action bar active when `selectedCount > 0` | `selectedCount`, `mode: 'gallery' \| 'album'` / `@add-to-album`, `@remove-from-album`, `@clear` |
| `AlbumGrid.vue` | Responsive album card grid (`1 col` mobile -> `2/3/4 cols` desktop) with 2x2 thumbnail collage | `albums`, `loading`, `canEdit` / `@open`, `@create`, `@rename`, `@delete` |
| `AlbumEditorDialog.vue` | Modal dialog to create or rename an album with client-side name validation | `open`, `mode: 'create' \| 'rename'`, `initialName`, `submitting`, `error` / `@submit`, `@close` |
| `AlbumPickerSheet.vue` | Mobile-friendly sheet/modal to assign selected photos to an existing or newly created album | `open`, `albums`, `submitting`, `error` / `@select-album`, `@create-and-add`, `@close` |
| `SettingsSectionCard.vue` | Clean grouped settings card container (`Card` + header + content slot) | `title`, `description?` + default slot |
| `AdminRefreshCard.vue` | Admin-only remote DB reload panel showing last counts and refresh trigger | `refreshing`, `statusMessage`, `error`, `lastResult` / `@refresh` |

---

## 7. Standard UX State & Accessibility Rules

1. **Skeleton Loading over Spinners:** Initial grid and album loads render `Skeleton` tiles matching grid geometry so layout does not jump when thumbnails arrive.
2. **Error Handling:** Network or proxy errors render `ErrorBanner` with an explicit retry button and technical `requestId` detail when available.
3. **Direct Lightbox Entry:** Tapping a media tile opens `MediaLightbox` immediately (avoiding intermediate action dialogs); batch album actions use explicit "Select" mode with `SelectionActionBar`.
4. **Accessibility Checklist:**
   * All icon-only buttons (`close`, `prev`, `next`, `theme toggle`, `back`, `info drawer`) include descriptive `aria-label`.
   * Dialogs and lightboxes trap keyboard focus, close on `Escape`, and restore focus on close.
   * `MediaLightbox` supports `ArrowLeft` / `ArrowRight` navigation and preserves visible focus outlines (`ring-ring`).
   * All images include meaningful `alt` text (derived caption/filename or date fallback).
