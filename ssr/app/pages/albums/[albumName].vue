<template>
  <q-page class="q-pa-md">
    <HeaderPageComponent :title="albumName" :subtitle="`${items.length} items`">
      <template #actions>
        <div class="row q-gutter-sm">
          <q-btn
            outline
            dense
            no-caps
            icon="checklist"
            :label="selectionMode ? 'Done' : 'Select'"
            @click="selectionMode = !selectionMode"
          />
          <q-btn flat dense no-caps icon="arrow_back" label="Back" to="/albums" />
        </div>
      </template>
    </HeaderPageComponent>

    <SelectionToolbar
      :selected-count="selectedHashes.length"
      show-remove-from-album
      @remove-from-album="removeSelected"
      @clear="selectedHashes = []"
    />

    <div v-if="loading" class="flex flex-center q-my-xl">
      <q-spinner size="42px" color="primary" />
    </div>

    <div v-else-if="items.length === 0" class="text-center text-grey-7 q-my-xl">
      This album is empty.
    </div>

    <FileGrid
      v-else
      :items="items"
      :selected-hashes="selectedHashes"
      :selection-mode="selectionMode"
      @open="openDetail"
      @toggle-select="toggleHash"
    />

    <FileDetailModal v-model="detailOpen" :item="activeItem" />
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useQuasar } from 'quasar'
import { useFirebaseAuth } from '../../composables/useFirebaseAuth'
import { usePhotosphereApi } from '../../composables/usePhotosphereApi'
import type { MediaItem } from '../../types'

const $q = useQuasar()
const route = useRoute()
const { isAuthenticated } = useFirebaseAuth()
const { fetchAlbumDetail, updateAlbum } = usePhotosphereApi()

const albumName = computed(() => decodeURIComponent(String(route.params.albumName || '')))
const items = ref<MediaItem[]>([])
const albumHashes = ref<string[]>([])
const loading = ref(false)
const selectionMode = ref(false)
const selectedHashes = ref<string[]>([])
const detailOpen = ref(false)
const activeItem = ref<MediaItem | null>(null)

const loadDetail = async () => {
  if (!isAuthenticated.value || !albumName.value) {
    return
  }
  loading.value = true
  try {
    const res = await fetchAlbumDetail(albumName.value)
    items.value = res.items
    albumHashes.value = res.album.hashes
  } finally {
    loading.value = false
  }
}

const toggleHash = (hash: string) => {
  if (selectedHashes.value.includes(hash)) {
    selectedHashes.value = selectedHashes.value.filter((h) => h !== hash)
  } else {
    selectedHashes.value = [...selectedHashes.value, hash]
  }
}

const removeSelected = async () => {
  const removeSet = new Set(selectedHashes.value)
  const remaining = albumHashes.value.filter((h) => !removeSet.has(h))
  await updateAlbum(albumName.value, remaining)
  selectedHashes.value = []
  selectionMode.value = false
  await loadDetail()
  $q.notify({ type: 'info', message: 'Removed items from album' })
}

const openDetail = (item: MediaItem) => {
  activeItem.value = item
  detailOpen.value = true
}

onMounted(() => {
  if (isAuthenticated.value) {
    loadDetail()
  }
})
</script>
