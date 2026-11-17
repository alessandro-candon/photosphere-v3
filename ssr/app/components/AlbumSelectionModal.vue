<template>
  <q-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)">
    <q-card style="min-width: 360px">
      <q-card-section class="text-h6"> Add {{ hashes.length }} item(s) to Album </q-card-section>

      <q-card-section class="q-gutter-md">
        <q-list bordered separator v-if="albums.length > 0">
          <q-item
            v-for="album in albums"
            :key="album.name"
            clickable
            v-ripple
            @click="addToExisting(album)"
          >
            <q-item-section>
              <q-item-label>{{ album.name }}</q-item-label>
              <q-item-label caption>{{ album.hashes.length }} items</q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-icon name="add_circle_outline" color="primary" />
            </q-item-section>
          </q-item>
        </q-list>

        <q-input
          v-model="newAlbumName"
          outlined
          dense
          label="Or create new album"
          placeholder="Summer 2026"
        />
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat label="Cancel" @click="$emit('update:modelValue', false)" />
        <q-btn
          color="primary"
          label="Create & Add"
          :loading="saving"
          :disable="!newAlbumName.trim()"
          @click="createAndAdd"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { usePhotosphereApi } from '../composables/usePhotosphereApi'
import type { AlbumRecord } from '../types'

const props = defineProps<{
  modelValue: boolean
  hashes: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [album: AlbumRecord]
}>()

const { fetchAlbums, createAlbum, updateAlbum } = usePhotosphereApi()
const albums = ref<AlbumRecord[]>([])
const newAlbumName = ref('')
const saving = ref(false)

const loadAlbums = async () => {
  try {
    const res = await fetchAlbums()
    albums.value = res.albums
  } catch {
    albums.value = []
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      loadAlbums()
    }
  }
)

onMounted(() => {
  if (props.modelValue) {
    loadAlbums()
  }
})

const addToExisting = async (album: AlbumRecord) => {
  saving.value = true
  try {
    const merged = Array.from(new Set([...album.hashes, ...props.hashes]))
    const res = await updateAlbum(album.name, merged)
    emit('saved', res.album)
    emit('update:modelValue', false)
  } finally {
    saving.value = false
  }
}

const createAndAdd = async () => {
  const name = newAlbumName.value.trim()
  if (!name) return
  saving.value = true
  try {
    const res = await createAlbum(name, props.hashes)
    newAlbumName.value = ''
    emit('saved', res.album)
    emit('update:modelValue', false)
  } finally {
    saving.value = false
  }
}
</script>
