<template>
  <div class="row q-col-gutter-sm items-center q-mb-md">
    <div class="col-12 col-md-6">
      <q-input
        v-model="localQuery"
        dense
        outlined
        clearable
        placeholder="Search labels, captions, or SHA-1..."
        @keyup.enter="emitSearch"
        @clear="emitSearch"
      >
        <template #append>
          <q-btn flat round dense icon="search" @click="emitSearch" />
        </template>
      </q-input>
    </div>

    <div v-if="suggestions.length > 0" class="col-12 col-md-6 row q-gutter-xs">
      <q-chip
        v-for="tag in suggestions"
        :key="tag"
        clickable
        size="sm"
        color="blue-1"
        text-color="primary"
        @click="selectSuggestion(tag)"
      >
        {{ tag }}
      </q-chip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { usePhotosphereApi } from '../composables/usePhotosphereApi'

const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  search: [value: string]
}>()

const { fetchSuggestions } = usePhotosphereApi()
const localQuery = ref(props.modelValue)
const suggestions = ref<string[]>([])

watch(
  () => props.modelValue,
  (val) => {
    localQuery.value = val
  }
)

watch(localQuery, async (val) => {
  const trimmed = (val || '').trim()
  if (trimmed.length < 2) {
    suggestions.value = []
    return
  }
  try {
    const res = await fetchSuggestions(trimmed)
    suggestions.value = [...res.labels.slice(0, 6), ...res.captions.slice(0, 2)]
  } catch {
    suggestions.value = []
  }
})

const emitSearch = () => {
  const value = (localQuery.value || '').trim()
  emit('update:modelValue', value)
  emit('search', value)
}

const selectSuggestion = (tag: string) => {
  localQuery.value = tag
  emitSearch()
}
</script>
