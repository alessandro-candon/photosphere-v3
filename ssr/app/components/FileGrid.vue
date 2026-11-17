<template>
  <div class="row q-col-gutter-md">
    <div v-for="item in items" :key="item.hash" class="col-6 col-sm-4 col-md-3 col-lg-2">
      <q-card
        class="cursor-pointer relative-position"
        bordered
        flat
        :class="{ 'bg-blue-1': selectedSet.has(item.hash) }"
        @click="handleCardClick(item)"
      >
        <div style="height: 180px" class="bg-grey-3 flex flex-center overflow-hidden">
          <img
            v-if="thumbUrls[item.hash]"
            :src="thumbUrls[item.hash]"
            :alt="item.caption || item.hash"
            style="width: 100%; height: 100%; object-fit: cover"
          />
          <q-icon
            v-else
            :name="item.fileType === 'VIDEO' ? 'videocam' : 'image'"
            size="48px"
            color="grey-6"
          />
        </div>

        <q-badge
          v-if="item.fileType === 'VIDEO'"
          color="dark"
          class="absolute-top-right q-ma-xs"
          label="VIDEO"
        />

        <q-checkbox
          v-if="selectionMode"
          :model-value="selectedSet.has(item.hash)"
          class="absolute-top-left"
          @click.stop
          @update:model-value="toggleSelect(item.hash)"
        />

        <q-card-section class="q-pa-xs">
          <div class="text-caption ellipsis">
            {{ item.caption || item.labels.slice(0, 3).join(', ') || item.hash.slice(0, 10) }}
          </div>
          <div class="text-caption text-grey-6">
            {{ formatShortDate(item.createdAtTimestamp) }}
          </div>
        </q-card-section>
      </q-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, watch } from 'vue'
import { usePhotosphereApi } from '../composables/usePhotosphereApi'
import type { MediaItem } from '../types'

const props = defineProps<{
  items: MediaItem[]
  selectedHashes: string[]
  selectionMode?: boolean
}>()

const emit = defineEmits<{
  open: [item: MediaItem]
  'toggle-select': [hash: string]
}>()

const { fetchMediaAsBlob } = usePhotosphereApi()
const thumbUrls = reactive<Record<string, string>>({})
let activeController: AbortController | null = null

const selectedSet = computed(() => new Set(props.selectedHashes))

const revokeAll = () => {
  for (const url of Object.values(thumbUrls)) {
    URL.revokeObjectURL(url)
  }
  for (const key of Object.keys(thumbUrls)) {
    delete thumbUrls[key]
  }
}

watch(
  () => props.items,
  async (nextItems) => {
    activeController?.abort()
    activeController = new AbortController()
    const signal = activeController.signal

    for (const item of nextItems) {
      const proxyPath = item.proxyUrls.thumbnailUrl
      if (!proxyPath || thumbUrls[item.hash]) {
        continue
      }
      try {
        thumbUrls[item.hash] = await fetchMediaAsBlob(proxyPath, signal)
      } catch {
        // ignore aborted or missing thumbnails
      }
    }
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  activeController?.abort()
  revokeAll()
})

const handleCardClick = (item: MediaItem) => {
  if (props.selectionMode) {
    emit('toggle-select', item.hash)
  } else {
    emit('open', item)
  }
}

const toggleSelect = (hash: string) => {
  emit('toggle-select', hash)
}

const formatShortDate = (ts: number | null): string => {
  if (!ts) return 'No date'
  const ms = ts < 1e11 ? ts * 1000 : ts
  return new Date(ms).toLocaleDateString()
}
</script>
