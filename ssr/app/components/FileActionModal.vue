<template>
  <q-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)">
    <q-card style="min-width: 300px" v-if="item">
      <q-card-section class="text-h6">Actions</q-card-section>
      <q-list>
        <q-item clickable @click="emitAction('view')">
          <q-item-section avatar><q-icon name="visibility" /></q-item-section>
          <q-item-section>Inspect Details</q-item-section>
        </q-item>
        <q-item clickable @click="emitAction('album')">
          <q-item-section avatar><q-icon name="collections" /></q-item-section>
          <q-item-section>Add to Album</q-item-section>
        </q-item>
      </q-list>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import type { MediaItem } from '../types'

defineProps<{
  modelValue: boolean
  item: MediaItem | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  action: [type: 'view' | 'album']
}>()

const emitAction = (type: 'view' | 'album') => {
  emit('action', type)
  emit('update:modelValue', false)
}
</script>
