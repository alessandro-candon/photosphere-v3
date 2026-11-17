<template>
  <q-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)">
    <q-card style="min-width: 360px">
      <q-card-section class="text-h6">Location Lookup</q-card-section>
      <q-card-section class="q-gutter-sm">
        <q-input
          v-model="queryText"
          outlined
          dense
          placeholder="Search city or landmark..."
          @keyup.enter="runSearch"
        >
          <template #append>
            <q-btn flat round dense icon="search" :loading="loading" @click="runSearch" />
          </template>
        </q-input>

        <div v-if="errorMsg" class="text-negative text-caption">{{ errorMsg }}</div>

        <q-list bordered separator v-if="results.length > 0">
          <q-item
            v-for="loc in results"
            :key="loc.displayName"
            clickable
            @click="$emit('select', loc)"
          >
            <q-item-section>
              <q-item-label>{{ loc.displayName }}</q-item-label>
              <q-item-label caption
                >{{ loc.lat.toFixed(4) }}, {{ loc.lon.toFixed(4) }}</q-item-label
              >
            </q-item-section>
          </q-item>
        </q-list>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn flat label="Close" @click="$emit('update:modelValue', false)" />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { usePhotosphereApi } from '../composables/usePhotosphereApi'
import type { LocationSearchResult } from '../types'

defineProps<{
  modelValue: boolean
}>()

defineEmits<{
  'update:modelValue': [value: boolean]
  select: [location: LocationSearchResult]
}>()

const { searchLocation } = usePhotosphereApi()
const queryText = ref('')
const results = ref<LocationSearchResult[]>([])
const loading = ref(false)
const errorMsg = ref('')

const runSearch = async () => {
  const q = queryText.value.trim()
  if (!q) return
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await searchLocation(q)
    results.value = res.results
  } catch (error) {
    errorMsg.value = error instanceof Error ? error.message : 'Location lookup failed'
    results.value = []
  } finally {
    loading.value = false
  }
}
</script>
