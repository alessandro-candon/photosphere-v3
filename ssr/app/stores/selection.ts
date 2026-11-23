import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export const useSelectionStore = defineStore('selection', () => {
  const selecting = ref(false)
  const selectedHashes = ref<Set<string>>(new Set())

  const selectedCount = computed(() => selectedHashes.value.size)
  const selectedList = computed(() => Array.from(selectedHashes.value))

  const setSelecting = (value: boolean) => {
    selecting.value = value
    if (!value) {
      selectedHashes.value = new Set()
    }
  }

  const toggleSelecting = () => {
    setSelecting(!selecting.value)
  }

  const toggleHash = (hash: string) => {
    const next = new Set(selectedHashes.value)
    if (next.has(hash)) {
      next.delete(hash)
    } else {
      next.add(hash)
    }
    selectedHashes.value = next
  }

  const selectAll = (hashes: string[]) => {
    selectedHashes.value = new Set(hashes)
    selecting.value = true
  }

  const clearSelection = () => {
    selectedHashes.value = new Set()
    selecting.value = false
  }

  return {
    selecting,
    selectedHashes,
    selectedCount,
    selectedList,
    setSelecting,
    toggleSelecting,
    toggleHash,
    selectAll,
    clearSelection,
  }
})
