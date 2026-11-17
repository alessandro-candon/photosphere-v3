<template>
  <q-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)">
    <q-card style="min-width: 340px">
      <q-card-section class="text-h6">Filter Media</q-card-section>
      <q-card-section class="q-gutter-md">
        <q-select
          v-model="draft.fileType"
          outlined
          dense
          emit-value
          map-options
          label="Media Type"
          :options="typeOptions"
        />
        <q-input v-model="draft.dateFrom" outlined dense type="date" label="From Date" />
        <q-input v-model="draft.dateTo" outlined dense type="date" label="To Date" />
        <q-toggle v-model="draft.hasLocation" label="Only geotagged items" />
      </q-card-section>
      <q-card-actions align="right">
        <q-btn flat label="Reset" @click="resetFilters" />
        <q-btn flat label="Cancel" @click="$emit('update:modelValue', false)" />
        <q-btn color="primary" label="Apply" @click="applyFilters" />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { MediaFilterState } from '../types'

const props = defineProps<{
  modelValue: boolean
  filters: MediaFilterState
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  apply: [filters: MediaFilterState]
}>()

const typeOptions = [
  { label: 'All Types', value: 'ALL' },
  { label: 'Images', value: 'IMAGE' },
  { label: 'Videos', value: 'VIDEO' },
]

const draft = reactive<MediaFilterState>({ ...props.filters })

watch(
  () => props.filters,
  (next) => {
    Object.assign(draft, next)
  },
  { deep: true }
)

const applyFilters = () => {
  emit('apply', { ...draft })
  emit('update:modelValue', false)
}

const resetFilters = () => {
  draft.q = ''
  draft.fileType = 'ALL'
  draft.album = ''
  draft.hasLocation = false
  draft.dateFrom = ''
  draft.dateTo = ''
  applyFilters()
}
</script>
