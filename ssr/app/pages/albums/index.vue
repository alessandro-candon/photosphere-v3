<template>
  <q-page class="q-pa-md">
    <HeaderPageComponent title="Albums" :subtitle="`${albums.length} albums`">
      <template #actions>
        <q-btn color="primary" icon="add" label="New Album" no-caps @click="createOpen = true" />
      </template>
    </HeaderPageComponent>

    <div v-if="loading" class="flex flex-center q-my-xl">
      <q-spinner size="42px" color="primary" />
    </div>

    <div v-else-if="albums.length === 0" class="text-center text-grey-7 q-my-xl">
      No albums created yet.
    </div>

    <div v-else class="row q-col-gutter-md">
      <div v-for="album in albums" :key="album.name" class="col-12 col-sm-6 col-md-4 col-lg-3">
        <q-card bordered flat>
          <q-card-section
            class="cursor-pointer"
            @click="navigateTo(`/albums/${encodeURIComponent(album.name)}`)"
          >
            <div class="text-h6 ellipsis">{{ album.name }}</div>
            <div class="text-caption text-grey-7">{{ album.hashes.length }} items</div>
          </q-card-section>
          <q-card-actions align="right">
            <q-btn
              flat
              dense
              color="primary"
              label="Open"
              :to="`/albums/${encodeURIComponent(album.name)}`"
            />
            <q-btn flat dense color="negative" icon="delete" @click="handleDelete(album.name)" />
          </q-card-actions>
        </q-card>
      </div>
    </div>

    <q-dialog v-model="createOpen">
      <q-card style="min-width: 320px">
        <q-card-section class="text-h6">Create Album</q-card-section>
        <q-card-section>
          <q-input v-model="newName" outlined dense label="Album Name" autofocus />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Cancel" @click="createOpen = false" />
          <q-btn color="primary" label="Create" :disable="!newName.trim()" @click="handleCreate" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { navigateTo } from '#imports'
import { useFirebaseAuth } from '../../composables/useFirebaseAuth'
import { usePhotosphereApi } from '../../composables/usePhotosphereApi'
import type { AlbumRecord } from '../../types'

const $q = useQuasar()
const { isAuthenticated } = useFirebaseAuth()
const { fetchAlbums, createAlbum, deleteAlbum } = usePhotosphereApi()

const albums = ref<AlbumRecord[]>([])
const loading = ref(false)
const createOpen = ref(false)
const newName = ref('')

const loadAlbums = async () => {
  if (!isAuthenticated.value) {
    return
  }
  loading.value = true
  try {
    const res = await fetchAlbums()
    albums.value = res.albums
  } finally {
    loading.value = false
  }
}

const handleCreate = async () => {
  const name = newName.value.trim()
  if (!name) return
  try {
    await createAlbum(name, [])
    newName.value = ''
    createOpen.value = false
    await loadAlbums()
    $q.notify({ type: 'positive', message: `Created album '${name}'` })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error instanceof Error ? error.message : 'Failed to create album',
    })
  }
}

const handleDelete = async (name: string) => {
  try {
    await deleteAlbum(name)
    await loadAlbums()
    $q.notify({ type: 'info', message: `Deleted album '${name}'` })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error instanceof Error ? error.message : 'Failed to delete album',
    })
  }
}

onMounted(() => {
  if (isAuthenticated.value) {
    loadAlbums()
  }
})
</script>
