import { ref, watch } from 'vue'
import { useAuthStore, type ThemeMode } from '../stores/auth'
import type { BasemapStyle, HeatmapDataMode, WorldHeatmapSettings } from '../types'

export const WORLD_HEATMAP_SETTINGS_KEY = 'world_heatmap_settings_v1'
export const HEATMAP_SETTINGS_UPDATED_EVENT = 'heatmap-settings-updated'

export const DEFAULT_WORLD_HEATMAP_SETTINGS: WorldHeatmapSettings = {
  basemap: 'dark',
  dataMode: 'geohash',
  dynamicRadius: true,
  baseRadius: 16,
  blur: 15,
  maxIntensity: 1.8,
  maxInspectResults: 30,
}

const VALID_BASEMAPS = new Set<BasemapStyle>(['dark', 'light', 'satellite'])
const VALID_DATA_MODES = new Set<HeatmapDataMode>(['geohash', 'raw'])

const clamp = (value: number, min: number, max: number): number =>
  Math.min(Math.max(value, min), max)

const parseClampedNumber = (
  raw: unknown,
  fallback: number,
  min: number,
  max: number,
  decimals = 0
): number => {
  const num = typeof raw === 'number' ? raw : typeof raw === 'string' ? Number(raw) : NaN
  if (!Number.isFinite(num)) return fallback
  const clamped = clamp(num, min, max)
  if (decimals === 0) return Math.round(clamped)
  const factor = 10 ** decimals
  return Math.round(clamped * factor) / factor
}

export const validateAndMergeMapSettings = (
  raw: unknown,
  fallbackTheme: ThemeMode = 'dark'
): WorldHeatmapSettings => {
  const defaultBasemap: BasemapStyle = fallbackTheme === 'light' ? 'light' : 'dark'
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return {
      ...DEFAULT_WORLD_HEATMAP_SETTINGS,
      basemap: defaultBasemap,
    }
  }

  const obj = raw as Record<string, unknown>
  const basemap =
    typeof obj.basemap === 'string' && VALID_BASEMAPS.has(obj.basemap as BasemapStyle)
      ? (obj.basemap as BasemapStyle)
      : defaultBasemap
  const dataMode =
    typeof obj.dataMode === 'string' && VALID_DATA_MODES.has(obj.dataMode as HeatmapDataMode)
      ? (obj.dataMode as HeatmapDataMode)
      : DEFAULT_WORLD_HEATMAP_SETTINGS.dataMode
  const dynamicRadius =
    typeof obj.dynamicRadius === 'boolean'
      ? obj.dynamicRadius
      : DEFAULT_WORLD_HEATMAP_SETTINGS.dynamicRadius

  return {
    basemap,
    dataMode,
    dynamicRadius,
    baseRadius: parseClampedNumber(
      obj.baseRadius,
      DEFAULT_WORLD_HEATMAP_SETTINGS.baseRadius,
      5,
      45,
      0
    ),
    blur: parseClampedNumber(obj.blur, DEFAULT_WORLD_HEATMAP_SETTINGS.blur, 5, 35, 0),
    maxIntensity: parseClampedNumber(
      obj.maxIntensity,
      DEFAULT_WORLD_HEATMAP_SETTINGS.maxIntensity,
      0.5,
      10.0,
      1
    ),
    maxInspectResults: parseClampedNumber(
      obj.maxInspectResults,
      DEFAULT_WORLD_HEATMAP_SETTINGS.maxInspectResults,
      10,
      200,
      0
    ),
  }
}

export const computeDynamicHeatOptions = (
  zoom: number,
  settings: WorldHeatmapSettings
): { radius: number; blur: number; max: number } => {
  const safeZoom = Number.isFinite(zoom) ? clamp(zoom, 2, 16) : 3
  if (!settings.dynamicRadius) {
    return {
      radius: settings.baseRadius,
      blur: settings.blur,
      max: settings.maxIntensity,
    }
  }

  const radius = clamp(Math.round(settings.baseRadius * (0.65 + (safeZoom - 2) * 0.08)), 5, 60)
  const blur = clamp(Math.round(settings.blur * (0.75 + (safeZoom - 2) * 0.05)), 5, 50)
  return {
    radius,
    blur,
    max: settings.maxIntensity,
  }
}

export const computeInspectRadiusKm = (zoom: number): number => {
  const safeZoom = Number.isFinite(zoom) ? clamp(zoom, 2, 16) : 3
  const rawKm = 100 * 2 ** (-Math.max(0, safeZoom - 4) * 0.75)
  const rounded = Math.round(rawKm * 100) / 100
  return clamp(rounded, 0.1, 100)
}

export const readMapSettingsFromStorage = (
  fallbackTheme: ThemeMode = 'dark'
): WorldHeatmapSettings => {
  if (typeof localStorage === 'undefined') {
    return validateAndMergeMapSettings(null, fallbackTheme)
  }
  try {
    const raw = localStorage.getItem(WORLD_HEATMAP_SETTINGS_KEY)
    if (!raw) {
      return validateAndMergeMapSettings(null, fallbackTheme)
    }
    const parsed = JSON.parse(raw) as unknown
    return validateAndMergeMapSettings(parsed, fallbackTheme)
  } catch {
    return validateAndMergeMapSettings(null, fallbackTheme)
  }
}

export const writeMapSettingsToStorage = (settings: WorldHeatmapSettings): void => {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(WORLD_HEATMAP_SETTINGS_KEY, JSON.stringify(settings))
  } catch {
    // Ignore quota or storage errors in restricted browsing modes
  }
}

const sharedSettings = ref<WorldHeatmapSettings>({ ...DEFAULT_WORLD_HEATMAP_SETTINGS })
let initialized = false
let listenersBound = false

export const resetSharedMapSettingsForTests = (): void => {
  initialized = false
  listenersBound = false
  sharedSettings.value = { ...DEFAULT_WORLD_HEATMAP_SETTINGS }
}

export const useMapSettings = () => {
  const authStore = useAuthStore()

  if (!initialized) {
    sharedSettings.value = readMapSettingsFromStorage(authStore.theme)
    initialized = true
  }

  const dispatchSettingsUpdated = (next: WorldHeatmapSettings) => {
    if (typeof window !== 'undefined' && typeof CustomEvent !== 'undefined') {
      window.dispatchEvent(new CustomEvent(HEATMAP_SETTINGS_UPDATED_EVENT, { detail: next }))
    }
  }

  const saveMapSettings = (
    partial: Partial<WorldHeatmapSettings>,
    options: { syncTheme?: boolean } = { syncTheme: true }
  ): WorldHeatmapSettings => {
    const merged = validateAndMergeMapSettings(
      { ...sharedSettings.value, ...partial },
      authStore.theme
    )
    sharedSettings.value = merged
    writeMapSettingsToStorage(merged)
    if (options.syncTheme !== false && (merged.basemap === 'dark' || merged.basemap === 'light')) {
      if (authStore.theme !== merged.basemap) {
        authStore.setTheme(merged.basemap)
      }
    }
    dispatchSettingsUpdated(merged)
    return merged
  }

  const resetMapSettings = (): WorldHeatmapSettings => {
    const defaults = validateAndMergeMapSettings(
      {
        ...DEFAULT_WORLD_HEATMAP_SETTINGS,
        basemap: authStore.theme === 'light' ? 'light' : 'dark',
      },
      authStore.theme
    )
    sharedSettings.value = defaults
    writeMapSettingsToStorage(defaults)
    dispatchSettingsUpdated(defaults)
    return defaults
  }

  const reloadMapSettings = (): WorldHeatmapSettings => {
    const loaded = readMapSettingsFromStorage(authStore.theme)
    sharedSettings.value = loaded
    return loaded
  }

  if (!listenersBound) {
    listenersBound = true

    watch(
      () => authStore.theme,
      (nextTheme) => {
        if (
          (sharedSettings.value.basemap === 'dark' || sharedSettings.value.basemap === 'light') &&
          sharedSettings.value.basemap !== nextTheme
        ) {
          saveMapSettings({ basemap: nextTheme }, { syncTheme: false })
        }
      }
    )

    if (typeof window !== 'undefined') {
      window.addEventListener('storage', (event: StorageEvent) => {
        if (event.key === WORLD_HEATMAP_SETTINGS_KEY) {
          sharedSettings.value = readMapSettingsFromStorage(authStore.theme)
        }
      })
    }
  }

  return {
    settings: sharedSettings,
    saveMapSettings,
    resetMapSettings,
    reloadMapSettings,
  }
}
