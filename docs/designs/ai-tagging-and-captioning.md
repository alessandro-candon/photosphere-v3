# AI Image Tagging, Captioning & Backfill (Moondream2)

* **Author:** alessandro-candon
* **Date:** 2026-11-17
* **Status:** Implemented

## Overview

`photosphere-v3` runs local vision AI tagging and captioning in `cli/` behind the `AIProvider` protocol (`cli/src/photosphere/ai/protocol.py`), using **Moondream2** (`vikhyatk/moondream2`) as the initial backend. For each novel photo or video during ingestion (or backfill via `photosphere annotate`), the provider generates a single-sentence English caption and up to 5 normalized descriptive tags (targeting 3–5, accepting fewer without padding), stored in `en_labels` / `en_captions` and translated via `EasyNMTTranslator`.

## Key Design Decisions

1. **Model Selection (`vikhyatk/moondream2`)**
   * Pinned model revision: `2025-06-21`
   * Pinned tokenizer (`moondream/starmie-v1`) revision: `35192e10a54e36eabe0a7cc57a2c1aab371cafc5`
   * Installed via optional extra `uv sync --extra ai` (`einops>=0.8.0`, `sacremoses>=0.1.1`, `sentencepiece>=0.2.0`, `torch>=2.5.0`, `transformers>=4.47.0`).
   * Weights are cached under `<cache_dir>/huggingface` (`trust_remote_code=True`).

2. **Native Host Execution (No Docker AI Support)**
   * AI inference targets native host execution (macOS MPS `bfloat16`, CUDA `bfloat16`/`float16`, or host CPU `float32`).
   * `cli/Dockerfile` does not bundle PyTorch or Moondream2 weights; when `auto` resolves to `cpu`, `load_optional_ai_provider` logs a pre-flight warning (`ai_cpu_fallback`).

3. **Input Resolution & Storage Contract**
   * The uploaded GCS thumbnail contract (`280x280` JPEG) is unchanged.
   * **Photos (`FileType.IMAGE`)**: decoded from `metadata.source_path` via `load_capped_rgb_image` in `cli/src/photosphere/media/image.py` (reusing `pillow_heif` and `ImageOps.exif_transpose()`, converted to `"RGB"`, capped at `1024px` max edge in memory).
   * **Videos (`FileType.VIDEO`)**: analyzed using the extracted `280x280` first-frame thumbnail (`metadata.thumbnail_path`).

4. **Lifecycle, Normalization & Failure Handling**
   * `IngestPipeline` lazy-loads and caches `AIProvider` once per `run()` and calls `release()` before `EasyNMTTranslator` runs.
   * Captions are normalized to a single sentence (`normalize_caption`); tags are lowercased, trimmed, deduplicated, stripped of numbering/punctuation/empty strings, and capped at 5 without padding (`normalize_tags`, `parse_tags_response`).
   * `AINotConfiguredError` fails fast; `AIInferenceError` retries up to `ai_max_retries` (default `1`, clearing MPS/CUDA cache between attempts) and, if exhausted, increments `ai_failed`, logs `ai_inference_failed` with `sha1`, and stores `label_indexes: []`, `caption_index: None`.

5. **Backfill Command (`photosphere annotate`)**
   * Scans `photosphere_database_cloud.json` for unannotated records (`label_indexes == []` and `caption_index is None`, or partial with `--include-partial`).
   * Reuses `find_similar_annotated_record` first, then checks `--local-media-dir` (if given), and otherwise defaults to downloading `thumbnail_bucket_uri` (`280x280`) to avoid Archive-class GCS retrieval fees (opt in to originals via `--use-source-bucket`).

## Alternatives Weighed

* **Tag2Text (`xinyu1205/Recognize_Anything-Tag2Text`):** Discarded because it requires an unmaintained older stack (`transformers==4.26.1`, Python 3.11) incompatible with `cli/pyproject.toml` (`>=3.12`, `transformers>=4.47.0`).
* **Florence-2 (`florence-base` / `florence-base-onnx`):** Not selected as primary backend; `<OD>` object-detection tags met the 3–5 tag target on only 5.6% (8/143) of benchmark images.
* **Qwen2.5-VL-3B / SmolVLM2:** Deferred; unbenchmarked on the target dataset, whereas Moondream2 was already used in `photosphere-v2` and met the 3–5 tag target on 97.9% (140/143) of benchmark images.

## Implemented Files

* `cli/pyproject.toml` — updated `[project.optional-dependencies] ai`
* `cli/src/photosphere/config.py` — `ai_max_image_size`, `ai_max_retries`
* `cli/src/photosphere/media/image.py` — `load_capped_rgb_image`
* `cli/src/photosphere/ai/normalize.py` — `normalize_caption`, `normalize_tags`, `parse_tags_response`
* `cli/src/photosphere/ai/protocol.py` — `AIInferenceError`, `resolve_dtype`, `empty_device_cache`, `release_ai_provider`, `analyze_with_retry`, `load_optional_ai_provider`
* `cli/src/photosphere/ai/moondream2.py` — `Moondream2Provider`
* `cli/src/photosphere/ai/__init__.py` — package exports
* `cli/src/photosphere/pipeline/ingest.py` — single-load caching, photo/video routing, retry/fallback, `ai_retried`/`ai_failed`
* `cli/src/photosphere/storage/gcs_client.py` — `download_blob`
* `cli/src/photosphere/pipeline/annotate.py` — `AnnotatePipeline`, `AnnotateSummary`
* `cli/src/photosphere/main.py` — `--device` on `ingest`, `photosphere annotate` command
* `cli/tests/test_ai_normalize.py`, `cli/tests/test_moondream2_provider.py`, `cli/tests/test_annotate_pipeline.py`, `cli/tests/test_ingest_pipeline.py`
