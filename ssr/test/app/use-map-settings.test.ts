import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  computeDynamicHeatOptions,
  computeInspectRadiusKm,
  DEFAULT_WORLD_HEATMAP_SETTINGS,
  HEATMAP_SETTINGS_UPDATED_EVENT,
  resetSharedMapSettingsForTests,
  useMapSettings,
  validateAndMergeMapSettings,
  WORLD_HEATMAP_SETTINGS_KEY,
} from '../../app/composables/useMapSettings'
import { useAuthStore } from '../../app/stores/auth'

const createMockStorage = () => {
  const store = new Map<string, string>()
  return {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value)
    },
    removeItem: (key: string) => {
      store.delete(key)
    },
    clear: () => {
      store.clear()
    },
  }
}

describe('useMapSettings composable & helpers', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    resetSharedMapSettingsForTests()
    vi.stubGlobal('localStorage', createMockStorage())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('merges defaults and clamps out-of-range values cleanly', () => {
    const fromNull = validateAndMergeMapSettings(null, 'light')
    expect(fromNull).toEqual({
      ...DEFAULT_WORLD_HEATMAP_SETTINGS,
      basemap: 'light',
    })

    const clamped = validateAndMergeMapSettings(
      {
        basemap: 'satellite',
        dataMode: 'raw',
        dynamicRadius: false,
        baseRadius: 999,
        blur: 1,
        maxIntensity: 42.789,
        maxInspectResults: 500,
      },
      'dark'
    )
    expect(clamped).toEqual({
      basemap: 'satellite',
      dataMode: 'raw',
      dynamicRadius: false,
      baseRadius: 45,
      blur: 5,
      maxIntensity: 10,
      maxInspectResults: 200,
    })
  })

  it('computes dynamic heat options and zoom-proportional inspect radius within [0.1, 100] km', () => {
    const staticOpts = computeDynamicHeatOptions(14, {
      ...DEFAULT_WORLD_HEATMAP_SETTINGS,
      dynamicRadius: false,
    })
    expect(staticOpts).toEqual({ radius: 16, blur: 15, max: 1.8 })

    const lowZoomOpts = computeDynamicHeatOptions(2, DEFAULT_WORLD_HEATMAP_SETTINGS)
    const highZoomOpts = computeDynamicHeatOptions(15, DEFAULT_WORLD_HEATMAP_SETTINGS)
    expect(highZoomOpts.radius).toBeGreaterThan(lowZoomOpts.radius)

    expect(computeInspectRadiusKm(2)).toBe(100)
    expect(computeInspectRadiusKm(4)).toBe(100)
    expect(computeInspectRadiusKm(10)).toBeLessThan(10)
    expect(computeInspectRadiusKm(16)).toBeGreaterThanOrEqual(0.1)
    expect(computeInspectRadiusKm(16)).toBeLessThan(0.5)
  })

  it('persists settings to localStorage, dispatches event, and syncs non-satellite basemap with theme', () => {
    const dispatchEvent = vi.fn()
    const addEventListener = vi.fn()
    vi.stubGlobal('window', { dispatchEvent, addEventListener })

    const authStore = useAuthStore()
    authStore.setTheme('dark')

    const { settings, saveMapSettings, resetMapSettings } = useMapSettings()
    expect(settings.value.basemap).toBe('dark')

    saveMapSettings({ basemap: 'light', baseRadius: 24, maxInspectResults: 60 })
    expect(authStore.theme).toBe('light')
    expect(JSON.parse(localStorage.getItem(WORLD_HEATMAP_SETTINGS_KEY) || '{}')).toMatchObject({
      basemap: 'light',
      baseRadius: 24,
      maxInspectResults: 60,
    })
    expect(dispatchEvent).toHaveBeenCalled()
    expect((dispatchEvent.mock.calls[0]?.[0] as CustomEvent).type).toBe(
      HEATMAP_SETTINGS_UPDATED_EVENT
    )

    // Satellite basemap is preserved when app theme toggles
    saveMapSettings({ basemap: 'satellite' })
    authStore.setTheme('dark')
    expect(settings.value.basemap).toBe('satellite')

    resetMapSettings()
    expect(settings.value.baseRadius).toBe(DEFAULT_WORLD_HEATMAP_SETTINGS.baseRadius)
    expect(settings.value.basemap).toBe('dark')
  })
})
