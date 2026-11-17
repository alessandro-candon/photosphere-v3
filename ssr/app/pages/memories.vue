<template>
  <q-page class="q-pa-md">
    <HeaderPageComponent title="Memories" subtitle="Timeline & geotagged highlights" />

    <div v-if="loading" class="flex flex-center q-my-xl">
      <q-spinner size="42px" color="primary" />
    </div>

    <div v-else-if="items.length === 0" class="text-center text-grey-7 q-my-xl">
      No geotagged memories indexed yet.
    </div>

    <FileGrid
      v-else
      :items="items"
      :selected-hashes="[]"
      :selection-mode="false"
      @open="openDetail"
    />

    <FileDetailModal v-model="detailOpen" :item="activeItem" />
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useFirebaseAuth } from '../composables/useFirebaseAuth'
import { usePhotosphereApi } from '../composables/usePhotosphereApi'
import type { MediaItem } from '../types'

const { isAuthenticated } = useFirebaseAuth()
const { fetchFiles } = usePhotosphereApi()

const items = ref<MediaItem[]>([])
const loading = ref(false)
const detailOpen = ref(false)
const activeItem = ref<MediaItem | null>(null)

const openDetail = (item: MediaItem) => {
  activeItem.value = item
  detailOpen.value = true
}

onMounted(async () => {
  if (!isAuthenticated.value) {
    return
  }
  loading.value = true
  try {
    const res = await fetchFiles({ hasLocation: true, limit: 60 })
    items.value = res.items
  } finally {
    loading.value = false
  }
})
</script>
