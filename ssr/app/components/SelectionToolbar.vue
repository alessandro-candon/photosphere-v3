<template>
  <q-banner v-if="selectedCount > 0" class="bg-blue-1 text-primary q-mb-md rounded-borders">
    <div class="row items-center justify-between">
      <div class="text-subtitle2">{{ selectedCount }} item(s) selected</div>
      <div class="row q-gutter-sm">
        <q-btn
          dense
          color="primary"
          icon="playlist_add"
          label="Add to Album"
          @click="$emit('add-to-album')"
        />
        <q-btn
          v-if="showRemoveFromAlbum"
          dense
          color="negative"
          icon="remove_circle_outline"
          label="Remove from Album"
          @click="$emit('remove-from-album')"
        />
        <q-btn dense flat label="Clear" @click="$emit('clear')" />
      </div>
    </div>
  </q-banner>
</template>

<script setup lang="ts">
defineProps<{
  selectedCount: number
  showRemoveFromAlbum?: boolean
}>()

defineEmits<{
  'add-to-album': []
  'remove-from-album': []
  clear: []
}>()
</script>
