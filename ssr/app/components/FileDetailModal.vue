<template>
  <q-dialog
    :model-value="modelValue"
    maximized
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <q-card class="bg-black text-white column" v-if="item">
      <q-toolbar class="bg-grey-10">
        <q-toolbar-title class="ellipsis">
          {{ item.caption || item.hash }}
        </q-toolbar-title>
        <q-btn
          flat
          round
          dense
          icon="collections"
          title="Add to album"
          @click="$emit('add-to-album', item)"
        />
        <q-btn flat round dense icon="close" @click="$emit('update:modelValue', false)" />
      </q-toolbar>

      <div class="col row q-pa-md items-center justify-center">
        <div class="col-12 col-md-8 flex flex-center">
          <q-spinner v-if="loadingMedia" size="48px" color="white" />
          <video
            v-else-if="item.fileType === 'VIDEO' && mediaObjectUrl"
            :src="mediaObjectUrl"
            controls
            autoplay
            style="max-height: 80vh; max-width: 100%"
          />
          <img
            v-else-if="mediaObjectUrl"
            :src="mediaObjectUrl"
            :alt="item.caption || item.hash"
            style="max-height: 80vh; max-width: 100%; object-fit: contain"
          />
          <div v-else class="text-grey-5">Preview unavailable</div>
        </div>

        <div class="col-12 col-md-4 q-pa-md bg-grey-9 rounded-borders">
          <div class="text-subtitle1 q-mb-sm">Metadata</div>
          <div class="text-caption q-mb-xs"><strong>SHA-1:</strong> {{ item.hash }}</div>
          <div class="text-caption q-mb-xs">
            <strong>Captured:</strong>
            {{ formatFullTimestamp(item.createdAtTimestamp, item.createdAt) }}
          </div>
          <div
            v-if="item.latitude !== null && item.longitude !== null"
            class="text-caption q-mb-xs"
          >
            <strong>Location:</strong> {{ item.latitude.toFixed(5) }},
            {{ item.longitude.toFixed(5) }}
          </div>
          <div v-if="item.caption" class="text-body2 q-my-sm">{{ item.caption }}</div>
          <div class="row q-gutter-xs q-mt-sm">
            <q-chip v-for="lbl in item.labels" :key="lbl" dense color="primary" text-color="white">
              {{ lbl }}
            </q-chip>
          </div>
        </div>
      </div>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { usePhotosphereApi } from '../composables/usePhotosphereApi'
import type { MediaItem } from '../types'

const props = defineProps<{
  modelValue: boolean
  item: MediaItem | null
}>()

defineEmits<{
  'update:modelValue': [value: boolean]
  'add-to-album': [item: MediaItem]
}>()

const { fetchMediaAsBlob, streamVideoObjectUrl } = usePhotosphereApi()
const mediaObjectUrl = ref<string | null>(null)
const loadingMedia = ref(false)
let controller: AbortController | null = null

const cleanupMedia = () => {
  controller?.abort()
  controller = null
  if (mediaObjectUrl.value) {
    URL.revokeObjectURL(mediaObjectUrl.value)
    mediaObjectUrl.value = null
  }
}

watch(
  () => [props.modelValue, props.item] as const,
  async ([open, nextItem]) => {
    cleanupMedia()
    if (!open || !nextItem?.proxyUrls.sourceUrl) {
      return
    }
    loadingMedia.value = true
    controller = new AbortController()
    try {
      mediaObjectUrl.value =
        nextItem.fileType === 'VIDEO'
          ? await streamVideoObjectUrl(nextItem.proxyUrls.sourceUrl, controller.signal)
          : await fetchMediaAsBlob(nextItem.proxyUrls.sourceUrl, controller.signal)
    } catch {
      mediaObjectUrl.value = null
    } finally {
      loadingMedia.value = false
    }
  }
)

onBeforeUnmount(() => {
  cleanupMedia()
})

const formatFullTimestamp = (ts: number | null, fallbackIso: string | null): string => {
  if (ts !== null && Number.isFinite(ts)) {
    const ms = ts < 1e11 ? ts * 1000 : ts
    return new Date(ms).toLocaleString()
  }
  if (fallbackIso) {
    return fallbackIso
  }
  return 'Unknown date'
}
</script>
