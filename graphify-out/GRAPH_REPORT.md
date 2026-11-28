# Graph Report - photosphere-v3  (2026-11-28)

## Corpus Check
- 221 files · ~2,325,425 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 16 file(s) not represented in the graph (top: (none) 7, .example 2, .toml 2)

## Summary
- 2419 nodes · 5431 edges · 156 communities (125 shown, 31 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 745 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6f8b420d`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- create_sample_jpeg
- map-aggregation.ts
- photosphere/media/__init__.py
- map.vue
- sync_target_language_dictionaries
- progress.py
- map-heatmap.test.ts
- package.json
- AINotConfiguredError
- pathlib
- database.py
- StorageOptions
- BootstrapProvisioner
- test_bootstrap.py
- usePhotosphereApi.ts
- useGalleryFilters.ts
- MediaAnnotation
- test_moondream2.py
- SearchFilterBar.vue
- types.ts
- KeyValueStore
- MediaRecord
- ingest.py
- Target Files to Create/Modify
- albums/index.vue
- command.py
- models.py
- CheckpointStore
- auth.service.ts
- settings.vue
- albums-cache.ts
- main.py
- [albumName].vue
- dependencies
- GoogleRestClient
- StorageSyncError
- MediaLightbox.vue
- useMapSettings.ts
- FakeBlob
- albums.schema.json
- Photosphere v3 SSR Webapp — Feature-by-Feature Recreation Roadmap
- cli
- video.py
- properties
- components.json
- tqdm_logger_factory
- media-cache.service.ts
- Photosphere
- annotate.py
- PhotosphereSettings
- stores/auth.ts
- properties
- Host-Native CLI Packaging and Cross-Platform Distribution
- properties
- FileType
- test_main.py
- Photosphere v3 SSR — Frontend Design System & Organism Component Architecture
- kv_dictionary.schema.json
- pipeline
- memories.vue
- file-database-cache.ts
- Implemented Files
- test_gcs_upload_errors_wrap_in_storage_sync_error
- media_database.schema.json
- 11. `./ssr/app/types/leaflet-heat.d.ts` (Create)
- scripts
- Marble Bust of Victor Hugo (S.00464)
- properties
- file-filters.ts
- Azov (151)
- Target Files to Create/Modify
- Goal Description
- photosphere_config.schema.json
- auth
- Hawker Hurricane R4118
- gcp
- Target Files to Create/Modify
- Avaceratops
- Charioteer of Delphi (Aurige de Delphes)
- Target Files to Create/Modify
- MapSettingsCard.vue
- devDependencies
- .prettierrc.json
- Agate de l'Esterel
- Fallen Autumn Maple Leaves
- Baska Voda Mountain Image
- MediaRecord
- items
- Sand Lizard (Lacerta agilis)
- Red-knobbed Starfish (Protoreaster linckii)
- tsconfig.json
- Afrovenator abakensis
- latitude
- longitude
- cache/index.ts
- Russet Potato Cultivar
- M. Nonius Balbus Equestrian Statue
- Nipponosaurus
- World Map Heatmap & Spatial Inspector
- Moondream2Provider
- average_hash
- caption_index
- created_at
- created_at_timestamp
- file_type
- thumbnail_bucket_uri
- storage-download.ts
- image.py
- Photosphere V3 App Icon / Logo (gif.gif)
- _PhotosphereJsonSource
- properties
- .created_at_timestamp
- Photosphere v3 Monorepo Scaffolding & Dual-Bucket JSON Architecture
- Photosphere V3
- photosphere_v3_icon.svg
- leaflet-heat.d.ts
- AlbumEditorDialog.vue
- Commands Reference
- CheckpointEntry
- Local Ingest Latency Reduction (macOS Metal & Cross-Platform PyTorch)
- photosphere
- pnpm-workspace.yaml allowBuilds
- Alternatives Considered
- Alternatives Considered
- EasyNMTTranslator
- checkpoint.py
- test_checkpoint.py
- Technical Plan (Architecture)
- Quick Start
- Using the Web App
- initializeMap
- contracts
- Critical User Journeys (CUJs)
- conftest.py
- Common Workflows
- infra
- Configuration, Cache & Environment Variables
- Photosphere v3 SSR Webapp
- 2026-11-15_DRIFT_REPORT.md
- Docker Compose Services (fake-gcs-server, init, cli, ssr)

## God Nodes (most connected - your core abstractions)
1. `PhotosphereSettings` - 54 edges
2. `KeyValueStore` - 49 edges
3. `IngestPipeline` - 46 edges
4. `MediaRecord` - 43 edges
5. `BootstrapProvisioner` - 40 edges
6. `h3` - 38 edges
7. `cli()` - 36 edges
8. `ingest()` - 35 edges
9. `StorageSyncError` - 33 edges
10. `EasyNMTTranslator` - 31 edges

## Surprising Connections (you probably didn't know these)
- `Alternative C: Continuing to Maintain `vikhyatk/moondream2` for Local AI Labeling` --references--> `AIProvider`  [INFERRED]
  docs/designs/photosphere-v3-scaffolding.md → cli/src/photosphere/ai/protocol.py
- `Future Improvements` --references--> `AIProvider`  [INFERRED]
  docs/designs/photosphere-v3-scaffolding.md → cli/src/photosphere/ai/protocol.py
- `Open Questions` --references--> `AIProvider`  [INFERRED]
  docs/designs/photosphere-v3-scaffolding.md → cli/src/photosphere/ai/protocol.py
- `The Problem` --references--> `KeyValueStore`  [INFERRED]
  docs/designs/photosphere-v3-scaffolding.md → cli/src/photosphere/ai/translator.py
- `The Problem` --references--> `_PhotosphereJsonSource`  [INFERRED]
  docs/designs/host-native-cli-packaging.md → cli/src/photosphere/config.py

## Import Cycles
- None detected.

## Communities (156 total, 31 thin omitted)

### Community 0 - "create_sample_jpeg"
Cohesion: 0.15
Nodes (15): create_sample_jpeg(), FakeAIProvider, make_gcs(), test_annotate_pipeline_backfills_only_unannotated_records(), test_chronological_routing_prefixes_dated_media_with_result(), test_dry_run_is_read_only_and_previews_keys_and_collisions(), test_dry_run_preview_ai_populates_planned_upload_labels_and_caption(), test_ingest_caches_provider_uses_source_path_and_handles_retry_fallback() (+7 more)

### Community 1 - "map-aggregation.ts"
Cohesion: 0.15
Nodes (20): 20. `./ssr/test/server/map-heatmap.test.ts` (Create), 4. [`./ssr/server/utils/file-database-cache.ts`](../../ssr/server/utils/file-database-cache.ts) (Modify), MediaFilterParams, encodeGeohash(), resolveGeohashPrecision(), aggregateViewportHeatmap(), clamp(), computeLogWeight() (+12 more)

### Community 2 - "photosphere/media/__init__.py"
Cohesion: 0.15
Nodes (9): cli, Host-Native Install & Diagnostics, Invariants, Package Boundary & Ownership, Verification, dms_to_decimal(), encode_geohash(), _narrow_interval() (+1 more)

### Community 3 - "map.vue"
Cohesion: 0.05
Nodes (36): {
  activeItem,
  activeDetail,
  detailLoading,
  hasPrev,
  hasNext,
  openLightbox,
  closeLightbox,
  prevItem,
  nextItem,
}, authStore, { canEditAlbums, isAuthenticated }, clearInspectOverlays(), closeInspector(), currentPrecision, effectiveMode, fallbackTriggered (+28 more)

### Community 6 - "map-heatmap.test.ts"
Cohesion: 0.08
Nodes (22): vitest, resetMediaLruCacheForTests(), invalidateAlbumsCache(), invalidateFileDatabaseCache(), sortMediaHashesDescending(), validateMediaDatabasePayload(), currentConfig, mockNuxtApp (+14 more)

### Community 7 - "package.json"
Cohesion: 0.06
Nodes (35): class-variance-authority, clsx, nuxt, @nuxt/kit, @pinia/nuxt, pino-pretty, prettier, reka-ui (+27 more)

### Community 8 - "AINotConfiguredError"
Cohesion: 0.07
Nodes (11): AIInferenceError, AINotConfiguredError, RemoteMoondreamProvider, _FakeResponse, test_remote_provider_adds_moondream_auth_for_official_host(), fake_urlopen(), test_remote_provider_auth_and_transient_errors(), test_remote_provider_sends_x_api_key_and_normalizes() (+3 more)

### Community 9 - "pathlib"
Cohesion: 0.11
Nodes (11): configure_hf_cache_env(), resolve_device(), resolve_dtype(), _normalize_whitespace(), _should_drop_parenthetical(), _strip_meta_parenthetical_notes(), _replace(), _strip_trailing_meta_note() (+3 more)

### Community 10 - "database.py"
Cohesion: 0.10
Nodes (11): AlbumRecord, KeyValueDictionary, MediaDatabase, SkippedEntry, SkippedManifest, validate_against_contract(), _load(), test_fixtures_pass_json_schemas_and_pydantic_models() (+3 more)

### Community 11 - "StorageOptions"
Cohesion: 0.38
Nodes (6): ServeMediaInput, StorageOptions, buildFirebaseMediaUploadUrl(), uploadDataFile(), UploadDataFileOptions, UploadDataFileResult

### Community 13 - "test_bootstrap.py"
Cohesion: 0.08
Nodes (17): _FakeResponse, _FakeRestRouter, _FakeSession, _setup_infra(), test_fast_path_prints_existing_config_without_network(), test_google_rest_client_overrides_adc_quota_project_and_retries_propagation(), __init__(), _propagation_handler() (+9 more)

### Community 14 - "usePhotosphereApi.ts"
Cohesion: 0.09
Nodes (20): Phase 1 — Media Proxy, Derived Indexes & Read-Only Gallery + Lightbox (`/`), Phase 2 — Unified Search, Suggestions & OSM Location Search, Phase 3 — "On This Day" Memories (`/memories`), Phase 4 — Writable Albums (`/albums`, `/albums/[albumName]`), Phase 5 — Settings & Admin Operations (`/settings`), Shared Contracts & State Boundaries, Target Files to Create, Modify, or Delete, Verification & Test Files (+12 more)

### Community 15 - "useGalleryFilters.ts"
Cohesion: 0.62
Nodes (5): firstString(), optionalNonNegativeInt(), optionalNumber(), parseSearchField(), useGalleryFilters()

### Community 16 - "MediaAnnotation"
Cohesion: 0.14
Nodes (9): analyze_with_retry(), format_hf_load_hint(), MediaAnnotation, test_analyze_with_retry_and_release(), analyze(), test_analyze_with_retry_prefers_analyze_image_when_supported(), analyze(), analyze_image() (+1 more)

### Community 17 - "test_moondream2.py"
Cohesion: 0.11
Nodes (7): _install_fake_torch_and_transformers(), test_moondream2_analyze_image_skips_disk_decode_and_logs_stage_timings(), test_moondream2_offline_uses_local_tokenizer_snapshot(), test_moondream2_provider_cpu_matches_bfloat16_vision_crops(), test_moondream2_provider_pins_revisions_and_normalizes(), test_moondream2_provider_raises_inference_error_on_runtime_failure(), create_sample_rgba_png()

### Community 18 - "SearchFilterBar.vue"
Cohesion: 0.09
Nodes (26): activeFilterCount, activeScopeLabel, applyDraftFilters(), clearQuery(), draftDateFrom, draftDateTo, draftFileType, draftLat (+18 more)

### Community 19 - "types.ts"
Cohesion: 0.16
Nodes (23): 10. [`./ssr/app/types/media.ts`](../../ssr/app/types/media.ts) (Modify), 7. `./ssr/server/api/map/heatmap.get.ts` (Create), BasemapStyle, DATE_ONLY_REGEX, HeatmapDataMode, HeatmapPointTuple, MediaFileType, MediaSortOrder (+15 more)

### Community 20 - "KeyValueStore"
Cohesion: 0.14
Nodes (9): KeyValueStore, test_key_value_store_index_consistency_across_all_mutations(), test_key_value_store_o1_index_from_mapping_and_load_file(), 3. `cli/src/photosphere/ai/translator.py` (Modify), 3. `KeyValueStore` Mutation Encapsulation (`cli/src/photosphere/ai/translator.py`), 6. Test Packaging & Unit Tests (`cli/tests/`), 9. `cli/tests/ai/test_translator.py` (Modify), Technical Plan (Architecture) (+1 more)

### Community 21 - "MediaRecord"
Cohesion: 0.06
Nodes (27): _decode_hash_bits(), find_similar_annotated_record(), hamming_distance_percentage(), PerceptualHashIndex, _similarity_from_decoded(), MediaRecord, commit_media_and_english_dbs(), load_remote_media_db() (+19 more)

### Community 22 - "ingest.py"
Cohesion: 0.08
Nodes (13): SkippedManager, MediaMetadata, _build_record_from_checkpoint(), _build_remote_object_key(), IngestPipeline, IngestSummary, PlannedUpload, truncate_label() (+5 more)

### Community 23 - "Target Files to Create/Modify"
Cohesion: 0.06
Nodes (43): 4. `ssr/server/utils/photosphere-config.ts` (Modify), 11. `./scripts/init/test_bootstrap.py` (Create), 12. `./cli/src/photosphere/config.py` (Modify), 14. `./cli/src/photosphere/pipeline/ingest.py` (Modify), 16. `./cli/tests/test_models_contracts.py` (Modify), 18. `./ssr/server/utils/photosphere-config.ts` (Create), 19. `./ssr/server/plugins/00.photosphere-config.ts` (Create), 1. `./contracts/photosphere_config.schema.json` (Create) (+35 more)

### Community 24 - "albums/index.vue"
Cohesion: 0.08
Nodes (23): albums, authStore, confirmDelete(), deleteOpen, deleteSubmitting, deleteTargetName, editorError, editorMode (+15 more)

### Community 25 - "command.py"
Cohesion: 0.12
Nodes (14): _build_options(), init_command(), _parse_emails(), _prompt_if_missing(), _resolve_storage_classes(), _resolve_templates_dir(), BootstrapConfigError, load_and_validate_config() (+6 more)

### Community 26 - "models.py"
Cohesion: 0.11
Nodes (10): AuthConfig, build_config_metadata(), ConfigMetadata, FirebaseConfig, GcpConfig, PhotosphereConfig, PipelineConfig, StorageConfig (+2 more)

### Community 28 - "auth.service.ts"
Cohesion: 0.10
Nodes (28): Open Questions, Phase 0 — Platform Foundations, Middleware Fixes & Auth Session, firebase-admin, pino, attachRequestLogger(), authenticateApiRequest(), assertAdminUser(), createMediaSessionCookieValue() (+20 more)

### Community 29 - "settings.vue"
Cohesion: 0.08
Nodes (23): lucide-vue-next, emit, emit, emit, emit, emit, navItems, props (+15 more)

### Community 30 - "albums-cache.ts"
Cohesion: 0.13
Nodes (32): h3, SearchSuggestionItem, AlbumMutationResult, albumsSingleFlight, AlbumSummaryDto, createAlbum(), deleteAlbum(), findAlbumIndexByName() (+24 more)

### Community 31 - "main.py"
Cohesion: 0.11
Nodes (23): _ai_runtime_options(), annotate(), _build_ai_overrides(), _build_gcs_client(), doctor(), ingest(), _inspect_cached_models(), prefetch_models() (+15 more)

### Community 32 - "[albumName].vue"
Cohesion: 0.05
Nodes (32): vue, iconComponent, iconMap, props, emit, useSearchAutocomplete(), actionError, albumName (+24 more)

### Community 33 - "dependencies"
Cohesion: 0.11
Nodes (18): dependencies, class-variance-authority, clsx, firebase, firebase-admin, h3, leaflet, leaflet.heat (+10 more)

### Community 34 - "GoogleRestClient"
Cohesion: 0.14
Nodes (3): GoogleRestClient, _parse_error_details(), RestApiError

### Community 35 - "StorageSyncError"
Cohesion: 0.08
Nodes (17): BucketClassError, _build_storage_client(), GCSStorageClient, resolve_credentials_source(), StorageConflictError, StorageSyncError, 1. `cli/src/photosphere/storage/gcs_client.py` (Modify), 1. GCS Precondition Conflict Handling (`cli/src/photosphere/storage/gcs_client.py`) (+9 more)

### Community 36 - "MediaLightbox.vue"
Cohesion: 0.10
Nodes (21): emit, imgFailed, onMainClick(), props, emit, emit, formattedDate, onKeyDown() (+13 more)

### Community 37 - "useMapSettings.ts"
Cohesion: 0.18
Nodes (17): 16. [`./ssr/app/pages/settings.vue`](../../ssr/app/pages/settings.vue) (Modify), 21. `./ssr/test/app/use-map-settings.test.ts` (Create), clamp(), computeInspectRadiusKm(), DEFAULT_WORLD_HEATMAP_SETTINGS, HEATMAP_SETTINGS_UPDATED_EVENT, parseClampedNumber(), readMapSettingsFromStorage() (+9 more)

### Community 38 - "FakeBlob"
Cohesion: 0.15
Nodes (3): FakeBlob, FakeBucket, FakeClient

### Community 39 - "albums.schema.json"
Cohesion: 0.12
Nodes (17): description, items, type, $id, items, additionalProperties, pattern, properties (+9 more)

### Community 40 - "Photosphere v3 SSR Webapp — Feature-by-Feature Recreation Roadmap"
Cohesion: 0.06
Nodes (31): Additional Resources, Alternative A: Client-Side `fetch()` + `URL.createObjectURL()` for Authenticated Media, Alternative B: Switching `media_bucket` from `ARCHIVE` to `STANDARD` GCS Storage Class, Alternative C: Client-Measured Justified-Row Masonry Grid, Alternative D: Porting v2's `hashList` / `excludeHashList` Query Params and Precision-5 Geohash Filter, Alternative E: Single Monolithic Design Document, Alternatives Considered, Critical User Journeys (CUJs) (+23 more)

### Community 41 - "cli"
Cohesion: 0.05
Nodes (38): cli(), _is_interactive_tty(), 13. `./cli/src/photosphere/storage/gcs_client.py` (Modify), 17. `./cli/tests/test_ingest_pipeline.py` (Modify), 1. Architecture & Provisioning Data Flow, 2. Unified Configuration Schema & Precedence, 3. REST API Provisioning Sequence & Interactive Console Fallback, 4. Consumer Integration, Fail-Fast Enforcement & Test-Only Emulator Boundary (+30 more)

### Community 42 - "video.py"
Cohesion: 0.13
Nodes (14): MediaDecodeError, _apply_frame_rotation(), _build_collage(), _compute_video_hash(), _extract_first_frame_jpeg(), _extract_video_metadata(), _first_frame_from_container(), _metadata_from_container() (+6 more)

### Community 43 - "properties"
Cohesion: 0.10
Nodes (20): minLength, type, minLength, type, minLength, type, additionalProperties, properties (+12 more)

### Community 44 - "components.json"
Cohesion: 0.12
Nodes (15): aliases, components, composables, lib, ui, utils, iconLibrary, $schema (+7 more)

### Community 45 - "tqdm_logger_factory"
Cohesion: 0.15
Nodes (6): _configure_logging(), tqdm_logger_factory(), _factory(), TqdmPrintLogger, test_tqdm_print_logger_writes_via_tqdm(), test_translator_progress_tracks_only_missing_entries()

### Community 46 - "media-cache.service.ts"
Cohesion: 0.09
Nodes (29): CacheRecord, locationCache, LocationSearchOptions, LocationSearchResultDto, resetLocationProxyForTests(), runWithRateLimit(), searchNominatimLocations(), withRateLimitMutex (+21 more)

### Community 47 - "Photosphere"
Cohesion: 0.22
Nodes (7): Photosphere, Prerequisites, Run the CLI via Docker, Run the Web App via Docker, Table of Contents, Troubleshooting, Using Docker (Last-Resort Alternative)

### Community 48 - "annotate.py"
Cohesion: 0.09
Nodes (12): AIProvider, load_optional_ai_provider(), release_ai_provider(), AnnotatePipeline, AnnotateSummary, _needs_annotation(), _parse_gs_uri(), create_ai_provider() (+4 more)

### Community 49 - "PhotosphereSettings"
Cohesion: 0.09
Nodes (11): ConfigFileError, default_models_dir(), normalize_profile_name(), PhotosphereSettings, profile_display_name(), profile_root_dir(), resolve_photosphere_config_path(), test_default_cache_dir_uses_home_photosphere_cache() (+3 more)

### Community 50 - "stores/auth.ts"
Cohesion: 0.14
Nodes (16): firebase, pinia, authStore, { initialized, isAuthenticated }, route, useFirebaseAuth(), authStore, { isAuthenticated, userEmail, logout } (+8 more)

### Community 51 - "properties"
Cohesion: 0.15
Nodes (13): minLength, type, enum, type, minLength, type, enum, type (+5 more)

### Community 52 - "Host-Native CLI Packaging and Cross-Platform Distribution"
Cohesion: 0.22
Nodes (8): Alternatives Considered, Architecture Overview, Goals, Host-Native CLI Packaging and Cross-Platform Distribution, Non-Goals, Overview, Technical Plan, The Problem

### Community 53 - "properties"
Cohesion: 0.14
Nodes (14): additionalProperties, type, minLength, type, properties, metadata, profile, storage (+6 more)

### Community 54 - "FileType"
Cohesion: 0.11
Nodes (11): classify_media_type(), compute_sha1(), VideoProcessor, FileType, test_compute_sha1_and_classify_media_type(), test_media_metadata_properties_and_decode_error(), test_video_processor_handles_narrowed_metadata_and_frame_errors(), test_video_processor_propagates_unexpected_exceptions() (+3 more)

### Community 55 - "test_main.py"
Cohesion: 0.23
Nodes (7): moondream2_tokenizer_snapshot_dir(), test_ingest_cli_dry_run_and_routing_mode(), test_prefetch_models_cli_invokes_provider_and_translator(), test_profile_confirmation_prompt_and_doctor_propagation(), test_translate_and_verify_db_catch_storage_sync_error(), test_verify_db_uses_load_remote_kv_store_and_handles_conflict(), test_version_and_doctor_cli()

### Community 56 - "Photosphere v3 SSR — Frontend Design System & Organism Component Architecture"
Cohesion: 0.11
Nodes (17): 1. Purpose & Document Boundary, 2. Frontend Stack & Configuration Contract, 3. Semantic Color Tokens (Light & Dark), 4. Typography, Spacing & Touch Ergonomics, 5. Responsive Layout & Deterministic Gallery Masonry, 6. Three-Tier Component Architecture & Directory Map, 7. Standard UX State & Accessibility Rules, Anti-FOUC Theme Initialization (+9 more)

### Community 57 - "kv_dictionary.schema.json"
Cohesion: 0.18
Nodes (10): additionalProperties, minLength, type, description, $id, propertyNames, pattern, $schema (+2 more)

### Community 58 - "pipeline"
Cohesion: 0.18
Nodes (11): minLength, type, additionalProperties, properties, required, type, default_lang, pipeline (+3 more)

### Community 59 - "memories.vue"
Cohesion: 0.12
Nodes (16): emit, emit, localError, newAlbumName, props, submitNewAlbum(), useAlbumPicker(), activeMonthDay (+8 more)

### Community 60 - "file-database-cache.ts"
Cohesion: 0.14
Nodes (9): buildDerivedMediaIndexes(), dbSingleFlight, dictSingleFlight, languageDictCache, loadSingleDictionaryWithFallback(), validateKeyValueDictionaryPayload(), isValidCoordinatePair(), LANG_REGEX (+1 more)

### Community 61 - "Implemented Files"
Cohesion: 0.13
Nodes (13): normalize_caption(), normalize_tags(), parse_tags_response(), load_capped_rgb_image(), test_normalize_caption_collapses_whitespace_and_keeps_first_sentence(), test_normalize_tags_accepts_fewer_than_three_without_padding(), test_normalize_tags_cleans_deduplicates_and_caps_at_five(), test_parse_tags_response_handles_json_and_delimited_fallback() (+5 more)

### Community 63 - "media_database.schema.json"
Cohesion: 0.20
Nodes (9): additionalProperties, $ref, description, $id, propertyNames, pattern, $schema, title (+1 more)

### Community 64 - "11. `./ssr/app/types/leaflet-heat.d.ts` (Create)"
Cohesion: 0.29
Nodes (6): 11. `./ssr/app/types/leaflet-heat.d.ts` (Create), leaflet, HeatLatLngTuple, HeatLayer, HeatMapOptions, leaflet

### Community 65 - "scripts"
Cohesion: 0.20
Nodes (10): scripts, build, dev, format, format:fix, generate, postinstall, preview (+2 more)

### Community 66 - "Marble Bust of Victor Hugo (S.00464)"
Cohesion: 0.25
Nodes (8): Auguste Rodin, Expressive Open-Mouthed Face, Musée Rodin, Paris, The Tempest (Rodin S.01092), Victor Hugo, Marble Bust of Victor Hugo (S.00464), White Marble, White Marble Sculpture

### Community 67 - "properties"
Cohesion: 0.22
Nodes (9): type, pattern, type, properties, geohash, hash, source_bucket_uri, pattern (+1 more)

### Community 68 - "file-filters.ts"
Cohesion: 0.17
Nodes (7): extractFileName(), filterMediaHashes(), MediaDetailDto, narrowHashesWithIndex(), parseDateBoundMs(), toMediaDetail(), toMediaGridItem()

### Community 69 - "Azov (151)"
Cohesion: 0.25
Nodes (7): Azov (151), Coastal Cityscape, Forward Gun Turret, Hull Number 151, Mast Radome, Project 775M, Russian Navy Ensign

### Community 70 - "Target Files to Create/Modify"
Cohesion: 0.13
Nodes (14): 10. `cli/tests/media/test_video.py` (Modify), 6. `cli/tests/<pkg>/__init__.py` (Create — 7 files), CLI Refactor Follow-ups (Post-Review Hardening), Critical User Journeys (CUJs), CUJ 2: Corrupt Video Stream Handling, Detailed Implementation Plan, Goals, Non-Functional Requirements (+6 more)

### Community 71 - "Goal Description"
Cohesion: 0.14
Nodes (13): Automated Tests, [DELETE] Legacy flat test files, Goal Description, Implementation Plan: CLI Clean-Code Refactoring, Optimization, Resilience & Mirrored Test Suite, Manual Verification, [MODIFY] [ingest.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/pipeline/ingest.py) & [annotate.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/pipeline/annotate.py), [NEW] 1:1 Mirrored test modules (keeping `conftest.py`, `test_config.py`, `test_main.py`, `test_progress.py` at `cli/tests/` root), [NEW] [common.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/pipeline/common.py) (+5 more)

### Community 72 - "photosphere_config.schema.json"
Cohesion: 0.25
Nodes (7): additionalProperties, description, $id, required, $schema, title, type

### Community 73 - "auth"
Cohesion: 0.14
Nodes (14): pattern, type, items, minItems, type, additionalProperties, properties, required (+6 more)

### Community 74 - "Hawker Hurricane R4118"
Cohesion: 0.25
Nodes (7): Fuselage Code UP-W, Hawker Hurricane R4118, RAF Fin Flash, RAF Roundel, Fixed Tailwheel, Three-Blade Propeller, Ventral Radiator

### Community 75 - "gcp"
Cohesion: 0.18
Nodes (11): additionalProperties, properties, required, type, minLength, type, minLength, type (+3 more)

### Community 76 - "Target Files to Create/Modify"
Cohesion: 0.07
Nodes (28): 11. `cli/README.md` (Modify), 12. `cli/tests/conftest.py`, `cli/tests/test_models_contracts.py`, and `cli/tests/test_ingest_pipeline.py` (Modify), 1. `contracts/photosphere_config.schema.json` (Modify), 2. `contracts/fixtures/valid_photosphere_config.json` and `photosphere.config.json` (Modify), 3. `scripts/init/models.py`, `scripts/init/cli.py`, and `scripts/init/provisioner.py` (Modify), 5. `cli/src/photosphere/config.py` (Modify), 6. `cli/src/photosphere/main.py` (Modify), 7. `cli/src/photosphere/models/database.py` and `cli/src/photosphere/dedup/skipped.py` (Modify) (+20 more)

### Community 77 - "Avaceratops"
Cohesion: 0.33
Nodes (5): Avaceratops, Beak and Brow Horns, Ceratopsian Dinosaur, Solid Neck Frill, Spotted Green and Ochre Skin

### Community 78 - "Charioteer of Delphi (Aurige de Delphes)"
Cohesion: 0.33
Nodes (5): Bronze Reins, Ancient Greek Bronze Sculpture, Charioteer of Delphi (Aurige de Delphes), Delphi Archaeological Museum, Greece, Long Pleated Tunic (Xystis)

### Community 79 - "Target Files to Create/Modify"
Cohesion: 0.11
Nodes (18): 7. `./cli/mise.toml`, `./cli/.python-version`, `./cli/pyproject.toml`, `./cli/ruff.toml`, `./cli/pyrightconfig.json`, `./cli/Dockerfile`, `./cli/.env.example` & `./cli/README.md` (Create), 12. `./ssr/app/composables/useMapSettings.ts` (Create), 13. [`./ssr/app/composables/useGalleryFilters.ts`](../../ssr/app/composables/useGalleryFilters.ts) (Modify), 14. [`./ssr/app/composables/usePhotosphereApi.ts`](../../ssr/app/composables/usePhotosphereApi.ts) (Modify), 15. `./ssr/app/components/organisms/MapSettingsCard.vue` (Create), 17. `./ssr/app/components/organisms/MapInspectDrawer.vue` (Create), 18. `./ssr/app/pages/map.vue` (Create), 19. [`./ssr/app/components/organisms/AppShell.vue`](../../ssr/app/components/organisms/AppShell.vue) (Modify) (+10 more)

### Community 80 - "MapSettingsCard.vue"
Cohesion: 0.18
Nodes (6): draft, handleReset(), handleSave(), { settings, saveMapSettings, resetMapSettings }, showToast(), toastMessage

### Community 81 - "devDependencies"
Cohesion: 0.20
Nodes (10): devDependencies, @nuxt/kit, @pinia/nuxt, pino-pretty, prettier, @types/leaflet, typescript, vitest (+2 more)

### Community 82 - ".prettierrc.json"
Cohesion: 0.33
Nodes (5): printWidth, semi, singleQuote, tabWidth, trailingComma

### Community 83 - "Agate de l'Esterel"
Cohesion: 0.40
Nodes (5): Black Background, Translucent Chalcedony Banding, Agate de l'Esterel, Reddish-Orange Banding, Agate de l'Esterel Specimen

### Community 84 - "Fallen Autumn Maple Leaves"
Cohesion: 0.70
Nodes (4): Fallen Autumn Maple Leaves, Autumn Forest Floor, Moss-covered Tree Branch, Japanese Squirrel (Sciurus lis)

### Community 85 - "Baska Voda Mountain Image"
Cohesion: 0.40
Nodes (5): Baška Voda, Croatia, Clear Blue Sky, Pine Forest Foreground, Baska Voda Mountain Image, Rocky Limestone Mountain Peak

### Community 86 - "MediaRecord"
Cohesion: 0.40
Nodes (5): $defs, MediaRecord, additionalProperties, required, type

### Community 87 - "items"
Cohesion: 0.40
Nodes (5): minimum, type, items, type, label_indexes

### Community 88 - "Sand Lizard (Lacerta agilis)"
Cohesion: 0.40
Nodes (4): Dorsal Spotted Scales, Dry Leaves and Twigs, Moss-covered Log, Sand Lizard (Lacerta agilis)

### Community 89 - "Red-knobbed Starfish (Protoreaster linckii)"
Cohesion: 0.40
Nodes (4): Live Rock and Coral Substrate, Marine Aquarium Habitat, Red-knobbed Starfish (Protoreaster linckii), Sandy Substrate

### Community 90 - "tsconfig.json"
Cohesion: 0.40
Nodes (4): ./.nuxt/tsconfig.json, compilerOptions, strict, extends

### Community 91 - "Afrovenator abakensis"
Cohesion: 0.50
Nodes (3): Afrovenator abakensis, Paleoart Illustration, Theropod Dinosaur

### Community 92 - "latitude"
Cohesion: 0.50
Nodes (4): maximum, minimum, type, latitude

### Community 93 - "longitude"
Cohesion: 0.50
Nodes (4): maximum, minimum, type, longitude

### Community 94 - "cache/index.ts"
Cohesion: 0.20
Nodes (6): 2. [`./ssr/server/types/cache/index.ts`](../../ssr/server/types/cache/index.ts) (Modify), Goals, GeohashClusterBucket, LanguageDictionaries, MediaDatabaseSnapshot, KeyValueDictionary

### Community 95 - "Russet Potato Cultivar"
Cohesion: 0.83
Nodes (4): Cut Potato Cross Section, Potato Sprouts, Russet Potato Cultivar, Russet Potato Cultivar With Sprouts Image

### Community 96 - "M. Nonius Balbus Equestrian Statue"
Cohesion: 0.67
Nodes (4): Marble Horse, M. Nonius Balbus Equestrian Statue, MANN (Museo Archeologico Nazionale di Napoli), Marcus Nonius Balbus

### Community 97 - "Nipponosaurus"
Cohesion: 0.50
Nodes (3): Hadrosaurid Dinosaur, Nipponosaurus, Yellow-Brown Striped Coloration

### Community 98 - "World Map Heatmap & Spatial Inspector"
Cohesion: 0.12
Nodes (16): 1. High-Level System Architecture & Data Flow, 4. Frontend Map Engine, Click-to-Inspect & Component Hierarchy, 5. Settings Persistence & Theme Synchronization (`useMapSettings.ts` & `MapSettingsCard.vue`), Click-to-Inspect Area & Non-Modal `MapInspectDrawer.vue`, Critical User Journeys (CUJs), CUJ 1: Global-to-Street Heatmap Exploration with Active Filters, CUJ 2: Click-to-Inspect Area, Pin on Map, and Full-Screen Lightbox Preview, CUJ 3: Configuring Map Preferences and Synchronizing Basemap Theme (+8 more)

### Community 99 - "Moondream2Provider"
Cohesion: 0.14
Nodes (4): moondream2_snapshot_dir(), Moondream2Provider, empty_device_cache(), Stage 1: Inference Fast-Path (`protocol.py`, `config.py`, `moondream2.py`, `remote.py`)

### Community 100 - "average_hash"
Cohesion: 0.67
Nodes (3): minLength, type, average_hash

### Community 101 - "caption_index"
Cohesion: 0.67
Nodes (3): minimum, type, caption_index

### Community 102 - "created_at"
Cohesion: 0.67
Nodes (3): minLength, type, created_at

### Community 103 - "created_at_timestamp"
Cohesion: 0.67
Nodes (3): minimum, type, created_at_timestamp

### Community 104 - "file_type"
Cohesion: 0.67
Nodes (3): enum, type, file_type

### Community 105 - "thumbnail_bucket_uri"
Cohesion: 0.67
Nodes (3): thumbnail_bucket_uri, pattern, type

### Community 106 - "storage-download.ts"
Cohesion: 0.22
Nodes (15): buildFirebaseMediaReadUrl(), downloadDataFile(), downloadDataFileWithMetadata(), DownloadedJsonResult, DownloadedMediaResult, downloadMediaObject(), ensureMountedVolumeDir(), ensureMountedVolumeDirAsync() (+7 more)

### Community 107 - "image.py"
Cohesion: 0.13
Nodes (9): create_jpeg_thumbnail_from_pil(), _extract_exif_metadata(), _extract_gps_pair(), ImageProcessor, _parse_exif_datetime(), test_exif_datetime_and_gps_parsers(), test_image_processor_raises_media_decode_error_on_corrupt_file(), test_image_processor_scales_thumbnails_transposes_exif_and_preserves_rgba() (+1 more)

### Community 108 - "Photosphere V3 App Icon / Logo (gif.gif)"
Cohesion: 0.67
Nodes (3): Camera Lens / Sphere Motif, Photosphere V3 App Icon / Logo (gif.gif), V3 Version Badge

### Community 113 - "properties"
Cohesion: 0.20
Nodes (10): minLength, type, minLength, type, properties, cli_version, hostname, updated_at (+2 more)

### Community 114 - ".created_at_timestamp"
Cohesion: 0.13
Nodes (15): 4. `./contracts/media_database.schema.json`, `./contracts/kv_dictionary.schema.json`, `./contracts/albums.schema.json` & `./contracts/fixtures/*.json` (Create), 3. API Contracts, 5. [`./ssr/server/utils/file-filters.ts`](../../ssr/server/utils/file-filters.ts) (Modify), 8. [`./ssr/server/api/files/index.get.ts`](../../ssr/server/api/files/index.get.ts) (Modify), Alternative A: Standalone Vanilla JavaScript Modules (`map-heatmap.js` & `map-settings.js`), Alternative B: Embedded In-Memory SQLite Database (`better-sqlite3` / `sql.js`), Alternative C: Unbounded `raw` Coordinate Mode at All Zoom Levels, Alternative D: Single Geohash Prefix Filtering for Click-to-Inspect (`geohash.startsWith(clickedPrefix)`) (+7 more)

### Community 115 - "Photosphere v3 Monorepo Scaffolding & Dual-Bucket JSON Architecture"
Cohesion: 0.18
Nodes (11): Additional Resources, Detailed Implementation Plan, Future Improvements, Goals, Non-Functional Requirements, Non-Goals, Open Questions, Overview (+3 more)

### Community 126 - "AlbumEditorDialog.vue"
Cohesion: 0.24
Nodes (8): emit, nameInput, onSubmit(), props, validationError, emit, onInput(), props

### Community 127 - "Commands Reference"
Cohesion: 0.22
Nodes (9): Commands Reference, `photosphere annotate`, `photosphere doctor` & `photosphere version`, `photosphere ingest <INPUT_DIR>`, `photosphere init`, `photosphere translate`, `photosphere verify-db`, Supported Media Formats (+1 more)

### Community 128 - "CheckpointEntry"
Cohesion: 0.22
Nodes (5): CheckpointEntry, Additional Resources, Future Improvements, Non-Functional Requirements, Non-Goals

### Community 129 - "Local Ingest Latency Reduction (macOS Metal & Cross-Platform PyTorch)"
Cohesion: 0.13
Nodes (14): Critical User Journeys (CUJs), CUJ 1: Fast Local Offline Ingest on macOS Metal (Apple M2 Pro), CUJ 2: Cross-Platform Local & Remote Parity, CUJ 3: Re-Running or Inspecting Latency Breakdown, Detailed Implementation Plan, Goals, Local Ingest Latency Reduction (macOS Metal & Cross-Platform PyTorch), Open Questions (+6 more)

### Community 132 - "Alternatives Considered"
Cohesion: 0.25
Nodes (8): Alternative A: Concurrent `ThreadPoolExecutor` for `caption()` and `query()` on MPS (`photosphere-v2` Pattern), Alternative B: Single Combined JSON Prompt (Caption + Tags in One `query()` Call), Alternative C: OS-Specific Runtimes (MLX, CoreML, llama.cpp/GGUF, ONNX) or `torch.compile` on MPS, Alternative D: Reusing `280px` JPEG Thumbnails as AI Input (`photosphere-v2` Pattern), Alternative E: `PIL.Image.draft()` Fast JPEG Decode, Alternative F: BK-Tree or LSH Index for Perceptual Deduplication, Alternative G: Separate `ai_max_image_size` Defaults for Local (`378px`) vs. Remote (`1024px`), Alternatives Considered

### Community 133 - "Alternatives Considered"
Cohesion: 0.25
Nodes (8): Alternative A: Retaining Protobuf (`photosphere_database_cloud.pb`), Alternative B: Keeping TinyDB (`{"_default": {"1": ...}}`) or Permanent Migration Logic Inside `cli/`, Alternative C: Continuing to Maintain `vikhyatk/moondream2` for Local AI Labeling, Alternative D: Moving `thumbnails/` from Archive GCS to Standard GCS, Alternative E: Switching SSR to GCS IAM V4 Signed URLs Instead of Firebase Token Proxy, Alternative F: Keying `photosphere_database_cloud.json` on `average_hash` and Auto-Skipping Visual Collisions, Alternative G: Evolving `../photosphere-v2` In Place Instead of Greenfield `photosphere-v3`, Alternatives Considered

### Community 136 - "test_checkpoint.py"
Cohesion: 0.47
Nodes (3): test_checkpoint_store_fails_fast_on_mid_file_corruption(), test_checkpoint_store_survives_trailing_truncated_line(), test_checkpoint_store_validates_routing_mode_and_clears()

### Community 137 - "Technical Plan (Architecture)"
Cohesion: 0.33
Nodes (6): 1. Monorepo Boundaries & Root `Makefile`, 2. End-to-End Architecture & Data Flow, 3. Shared Data Contracts (`contracts/`) & Dual-Bucket Layout, 5. Nuxt SSR Application Design (`ssr/`), 6. Disposable Migration Script (`scripts/migrate_v2_to_v3.py`) & Cloud Infra (`infra/`), Technical Plan (Architecture)

### Community 138 - "Quick Start"
Cohesion: 0.33
Nodes (6): 1. Install the CLI, 2. Set Up Your Cloud Project, 3. Verify Your Setup, 4. Upload Your First Photos & Videos, 5. Open the Web App, Quick Start

### Community 139 - "Using the Web App"
Cohesion: 0.33
Nodes (6): Albums, Media Viewer (Lightbox), Memories, Photos & Search, Settings & Admin Refresh, Using the Web App

### Community 140 - "initializeMap"
Cohesion: 0.25
Nodes (9): leaflet.heat, computeDynamicHeatOptions(), applyBasemap(), applyHeatLayerOptions(), buildEsriBasemapLayer(), fetchHeatmapForCurrentViewport(), handleExternalSettingsEvent(), initializeMap() (+1 more)

### Community 141 - "contracts"
Cohesion: 0.40
Nodes (4): contracts, Invariants, Package Boundary & Ownership, Verification

### Community 142 - "Critical User Journeys (CUJs)"
Cohesion: 0.40
Nodes (5): Critical User Journeys (CUJs), CUJ 1: Unified Root Makefile Development & Verification, CUJ 2: Local Media Ingestion, Deduplication & Dual-Bucket Sync via CLI, CUJ 3: One-Time Disposable v2-to-v3 Database Migration, CUJ 4: Authenticated SSR Browsing, Search & Album Updates

### Community 143 - "conftest.py"
Cohesion: 0.09
Nodes (6): cli_settings(), create_sample_mp4(), fake_translator(), test_skipped_manager_moves_collision_safely_and_logs_manifest(), test_end_to_end_ingest_no_ai_then_annotate_then_verify_db(), test_gcs_storage_client_enforces_bucket_classes_and_aborts_on_missing_db()

### Community 144 - "Common Workflows"
Cohesion: 0.50
Nodes (4): Common Workflows, Fast Upload Now, AI Tag Later, Fully Offline AI & Translation, Using a Remote AI Server

### Community 145 - "infra"
Cohesion: 0.50
Nodes (3): infra, Package Boundary & Ownership, Provisioning Workflow

### Community 146 - "Configuration, Cache & Environment Variables"
Cohesion: 0.40
Nodes (5): Configuration, Cache & Environment Variables, Shared vs. Profile-Scoped Directories (`~/.photosphere/`), Useful Environment Variables, Where Photosphere Looks for Google Cloud Credentials, Where Photosphere Looks for `photosphere.config.json`

### Community 147 - "Photosphere v3 SSR Webapp"
Cohesion: 0.50
Nodes (3): Architecture, Commands, Photosphere v3 SSR Webapp

## Knowledge Gaps
- **627 isolated node(s):** `photosphere`, `$schema`, `$id`, `title`, `description` (+622 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1105 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **31 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MediaRecord` connect `MediaRecord` to `create_sample_jpeg`, `sync_target_language_dictionaries`, `Photosphere v3 SSR Webapp — Feature-by-Feature Recreation Roadmap`, `database.py`, `usePhotosphereApi.ts`, `annotate.py`, `.created_at_timestamp`, `ingest.py`, `main.py`?**
  _High betweenness centrality (0.207) - this node is a cross-community bridge._
- **Why does `Phase 1 — Media Proxy, Derived Indexes & Read-Only Gallery + Lightbox (`/`)` connect `usePhotosphereApi.ts` to `types.ts`, `memories.vue`, `MediaRecord`?**
  _High betweenness centrality (0.162) - this node is a cross-community bridge._
- **Why does `MediaGridItem` connect `usePhotosphereApi.ts` to `map.vue`, `MediaLightbox.vue`, `file-filters.ts`, `Target Files to Create/Modify`, `.created_at_timestamp`, `types.ts`?**
  _High betweenness centrality (0.074) - this node is a cross-community bridge._
- **Are the 39 inferred relationships involving `PhotosphereSettings` (e.g. with `_build_gcs_client()` and `doctor()`) actually correct?**
  _`PhotosphereSettings` has 39 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `KeyValueStore` (e.g. with `Package Boundary & Ownership` and `KeyValueDictionary`) actually correct?**
  _`KeyValueStore` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `IngestPipeline` (e.g. with `ingest()` and `AIProvider`) actually correct?**
  _`IngestPipeline` has 29 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `MediaRecord` (e.g. with `find_similar_annotated_record()` and `PerceptualHashIndex`) actually correct?**
  _`MediaRecord` has 19 INFERRED edges - model-reasoned connections that need verification._