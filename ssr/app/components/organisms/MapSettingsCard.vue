<template>
  <SettingsSectionCard
    title="Map & Heatmap Settings"
    description="Configure basemap style, spatial aggregation mode, heatmap rendering, and area inspector limits. Saved locally in your browser."
  >
    <form class="space-y-5" @submit.prevent="handleSave">
      <div class="grid gap-4 sm:grid-cols-2">
        <div class="space-y-1.5">
          <label for="map-basemap-select" class="block text-sm font-medium text-foreground">
            Basemap Style
          </label>
          <Select
            id="map-basemap-select"
            :model-value="draft.basemap"
            @update:model-value="onBasemapChange"
          >
            <option value="dark">Dark (Esri Dark Gray)</option>
            <option value="light">Light (Esri Light Gray)</option>
            <option value="satellite">Satellite (Esri World Imagery)</option>
          </Select>
          <p class="text-xs text-muted-foreground">
            Dark and Light sync with the application appearance theme; Satellite stays independent.
          </p>
        </div>

        <div class="space-y-1.5">
          <label for="map-datamode-select" class="block text-sm font-medium text-foreground">
            Data Mode
          </label>
          <Select
            id="map-datamode-select"
            :model-value="draft.dataMode"
            @update:model-value="onDataModeChange"
          >
            <option value="geohash">Geohash Aggregated (Recommended)</option>
            <option value="raw">Raw Points (Auto-clusters above 5,000)</option>
          </Select>
          <p class="text-xs text-muted-foreground">
            Geohash mode groups points by zoom precision for fast rendering across 100K+ items.
          </p>
        </div>
      </div>

      <div
        class="flex items-center justify-between gap-3 rounded-lg border border-border bg-muted/30 px-3.5 py-2.5"
      >
        <div class="space-y-0.5">
          <label for="map-dynamic-radius" class="block text-sm font-medium text-foreground">
            Dynamic Zoom Radius
          </label>
          <p class="text-xs text-muted-foreground">
            Automatically scale heatmap radius and blur proportionally as you zoom in or out.
          </p>
        </div>
        <input
          id="map-dynamic-radius"
          v-model="draft.dynamicRadius"
          type="checkbox"
          class="h-4 w-4 accent-primary cursor-pointer"
        />
      </div>

      <div class="grid gap-4 sm:grid-cols-2">
        <div class="space-y-1.5">
          <div class="flex items-center justify-between text-sm">
            <label for="map-base-radius" class="font-medium text-foreground">
              Base Heatmap Radius
            </label>
            <span class="font-mono text-xs text-muted-foreground">{{ draft.baseRadius }} px</span>
          </div>
          <input
            id="map-base-radius"
            v-model.number="draft.baseRadius"
            type="range"
            min="5"
            max="45"
            step="1"
            class="w-full accent-primary cursor-pointer"
          />
          <div class="flex justify-between text-[11px] text-muted-foreground">
            <span>5 px</span>
            <span>45 px</span>
          </div>
        </div>

        <div class="space-y-1.5">
          <div class="flex items-center justify-between text-sm">
            <label for="map-blur" class="font-medium text-foreground">Blur</label>
            <span class="font-mono text-xs text-muted-foreground">{{ draft.blur }} px</span>
          </div>
          <input
            id="map-blur"
            v-model.number="draft.blur"
            type="range"
            min="5"
            max="35"
            step="1"
            class="w-full accent-primary cursor-pointer"
          />
          <div class="flex justify-between text-[11px] text-muted-foreground">
            <span>5 px</span>
            <span>35 px</span>
          </div>
        </div>

        <div class="space-y-1.5">
          <div class="flex items-center justify-between text-sm">
            <label for="map-max-intensity" class="font-medium text-foreground">
              Max Intensity
            </label>
            <span class="font-mono text-xs text-muted-foreground">
              {{ draft.maxIntensity.toFixed(1) }}
            </span>
          </div>
          <input
            id="map-max-intensity"
            v-model.number="draft.maxIntensity"
            type="range"
            min="0.5"
            max="10"
            step="0.1"
            class="w-full accent-primary cursor-pointer"
          />
          <div class="flex justify-between text-[11px] text-muted-foreground">
            <span>0.5</span>
            <span>10.0</span>
          </div>
        </div>

        <div class="space-y-1.5">
          <label for="map-max-inspect" class="block text-sm font-medium text-foreground">
            Inspector Page Limit (10–200)
          </label>
          <Input
            id="map-max-inspect"
            :model-value="String(draft.maxInspectResults)"
            type="number"
            min="10"
            max="200"
            step="1"
            @update:model-value="onMaxInspectChange"
          />
        </div>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-3 pt-1">
        <div class="flex flex-wrap items-center gap-2">
          <Button type="submit" variant="default">
            <Save class="h-4 w-4" />
            <span>Save Settings</span>
          </Button>
          <Button type="button" variant="outline" @click="handleReset">
            <RotateCcw class="h-4 w-4" />
            <span>Reset Defaults</span>
          </Button>
        </div>

        <div
          v-if="toastMessage"
          role="status"
          aria-live="polite"
          class="inline-flex items-center gap-1.5 rounded-lg border border-primary/30 bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary"
        >
          <Check class="h-3.5 w-3.5" />
          <span>{{ toastMessage }}</span>
        </div>
      </div>
    </form>
  </SettingsSectionCard>
</template>

<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Check, RotateCcw, Save } from 'lucide-vue-next'
import SettingsSectionCard from './SettingsSectionCard.vue'
import Button from '../ui/Button.vue'
import Input from '../ui/Input.vue'
import Select from '../ui/Select.vue'
import { useMapSettings } from '../../composables/useMapSettings'
import type { BasemapStyle, HeatmapDataMode, WorldHeatmapSettings } from '../../types'

const { settings, saveMapSettings, resetMapSettings } = useMapSettings()

const draft = reactive<WorldHeatmapSettings>({ ...settings.value })
const toastMessage = ref('')
let toastTimer: ReturnType<typeof setTimeout> | null = null

watch(
  settings,
  (next) => {
    Object.assign(draft, next)
  },
  { deep: true }
)

const showToast = (message: string) => {
  toastMessage.value = message
  if (toastTimer) {
    clearTimeout(toastTimer)
  }
  toastTimer = setTimeout(() => {
    toastMessage.value = ''
  }, 3000)
}

const onBasemapChange = (value: string) => {
  if (value === 'dark' || value === 'light' || value === 'satellite') {
    draft.basemap = value as BasemapStyle
  }
}

const onDataModeChange = (value: string) => {
  if (value === 'geohash' || value === 'raw') {
    draft.dataMode = value as HeatmapDataMode
  }
}

const onMaxInspectChange = (value: string | number) => {
  const num = Number(value)
  if (Number.isFinite(num)) {
    draft.maxInspectResults = num
  }
}

const handleSave = () => {
  const saved = saveMapSettings({ ...draft })
  Object.assign(draft, saved)
  showToast('Map settings saved.')
}

const handleReset = () => {
  const defaults = resetMapSettings()
  Object.assign(draft, defaults)
  showToast('Map settings restored to defaults.')
}

onBeforeUnmount(() => {
  if (toastTimer) {
    clearTimeout(toastTimer)
  }
})
</script>
