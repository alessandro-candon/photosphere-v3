<template>
  <q-page class="q-pa-md">
    <HeaderPageComponent title="Library" :subtitle="`${total} items indexed (${lang})`">
      <template #actions>
        <div class="row q-gutter-sm">
          <q-btn
            outline
            dense
            no-caps
            :color="selectionMode ? 'primary' : 'grey-8'"
            icon="checklist"
            :label="selectionMode ? 'Done' : 'Select'"
            @click="toggleSelectionMode"
          />
          <q-btn
            outline
            dense
            no-caps
            icon="filter_list"
            label="Filter"
            @click="filterOpen = true"
          />
          <q-btn outline dense no-caps icon="place" label="Location" @click="locationOpen = true" />
        </div>
      </template>
    </HeaderPageComponent>

    <SearchBar v-model="filters.q" @search="loadPage(1)" />

    <SelectionToolbar
      :selected-count="selectedHashes.length"
      @add-to-album="albumModalOpen = true"
      @clear="selectedHashes = []"
    />

    <div v-if="loading" class="flex flex-center q-my-xl">
      <q-spinner size="42px" color="primary" />
    </div>

    <div v-else-if="items.length === 0" class="text-center text-grey-7 q-my-xl">
      No matching media items found.
    </div>

    <FileGrid
      v-else
      :items="items"
      :selected-hashes="selectedHashes"
      :selection-mode="selectionMode"
      @open="openDetail"
      @toggle-select="toggleHash"
    />

    <div v-if="totalPages > 1" class="flex flex-center q-mt-lg">
      <q-pagination v-model="page" :max="totalPages" input @update:model-value="loadPage" />
    </div>

    <FilterFab v-model="filterOpen" :filters="filters" @apply="onApplyFilters" />
    <LocationModal v-model="locationOpen" @select="locationOpen = false" />
    <FileDetailModal v-model="detailOpen" :item="activeItem" @add-to-album="openAlbumForItem" />
    <AlbumSelectionModal
      v-model="albumModalOpen"
      :hashes="albumTargetHashes"
      @saved="onAlbumSaved"
    />
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useFirebaseAuth } from '../composables/useFirebaseAuth'
import { usePhotosphereApi } from '../composables/usePhotosphereApi'
import type { MediaFilterState, MediaItem } from '../types'

const $q = useQuasar()
const { isAuthenticated } = useFirebaseAuth()
const { fetchFiles } = usePhotosphereApi()

const items = ref<MediaItem[]>([])
const total = ref(0)
const page = ref(1)
const totalPages = ref(1)
const lang = ref('en')
const loading = ref(false)

const selectionMode = ref(false)
const selectedHashes = ref<string[]>([])
const filterOpen = ref(false)
const locationOpen = ref(false)
const detailOpen = ref(false)
const albumModalOpen = ref(false)
const activeItem = ref<MediaItem | null>(null)
const singleAlbumHashes = ref<string[] | null>(null)

const filters = reactive<MediaFilterState>({
  q: '',
  fileType: 'ALL',
  album: '',
  hasLocation: false,
  dateFrom: '',
  dateTo: '',
})

const albumTargetHashes = computed(() => singleAlbumHashes.value ?? selectedHashes.value)

const loadPage = async (nextPage = 1) => {
  if (!isAuthenticated.value) {
    return
  }
  loading.value = true
  page.value = nextPage
  try {
    const res = await fetchFiles({ ...filters, page: nextPage, limit: 60 })
    items.value = res.items
    total.value = res.total
    totalPages.value = res.totalPages
    lang.value = res.lang
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error instanceof Error ? error.message : 'Failed to load media library',
    })
  } finally {
    loading.value = false
  }
}

const toggleSelectionMode = () => {
  selectionMode.value = !selectionMode.value
  if (!selectionMode.value) {
    selectedHashes.value = []
  }
}

const toggleHash = (hash: string) => {
  if (selectedHashes.value.includes(hash)) {
    selectedHashes.value = selectedHashes.value.filter((h) => h !== hash)
  } else {
    selectedHashes.value = [...selectedHashes.value, hash]
  }
}

const openDetail = (item: MediaItem) => {
  activeItem.value = item
  detailOpen.value = true
}

const openAlbumForItem = (item: MediaItem) => {
  singleAlbumHashes.value = [item.hash]
  albumModalOpen.value = true
}

const onApplyFilters = (next: MediaFilterState) => {
  Object.assign(filters, next)
  loadPage(1)
}

const onAlbumSaved = () => {
  singleAlbumHashes.value = null
  selectedHashes.value = []
  selectionMode.value = false
  $q.notify({ type: 'positive', message: 'Album updated' })
}

onMounted(() => {
  if (isAuthenticated.value) {
    loadPage(1)
  }
})
</script>
