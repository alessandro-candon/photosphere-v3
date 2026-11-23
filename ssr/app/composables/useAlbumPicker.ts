import { ref } from 'vue'
import type { AlbumSummary } from '../types'
import { usePhotosphereApi } from './usePhotosphereApi'

export const useAlbumPicker = () => {
  const { listAlbums, createAlbum, updateAlbum } = usePhotosphereApi()

  const pickerOpen = ref(false)
  const targetHashes = ref<string[]>([])
  const albums = ref<AlbumSummary[]>([])
  const albumsLoading = ref(false)
  const submitting = ref(false)
  const pickerError = ref('')

  const openPicker = async (hashes: string[]) => {
    if (hashes.length === 0) return
    targetHashes.value = [...hashes]
    pickerError.value = ''
    pickerOpen.value = true
    albumsLoading.value = true
    try {
      const response = await listAlbums(1, 100)
      albums.value = response.items
    } catch (error) {
      pickerError.value = error instanceof Error ? error.message : 'Failed to load albums'
    } finally {
      albumsLoading.value = false
    }
  }

  const closePicker = () => {
    pickerOpen.value = false
    targetHashes.value = []
    pickerError.value = ''
  }

  const addToExistingAlbum = async (albumName: string, onSuccess?: () => void) => {
    submitting.value = true
    pickerError.value = ''
    try {
      await updateAlbum(albumName, { addHashes: targetHashes.value })
      closePicker()
      onSuccess?.()
    } catch (error) {
      pickerError.value = error instanceof Error ? error.message : 'Failed to update album'
    } finally {
      submitting.value = false
    }
  }

  const createAlbumWithSelection = async (albumName: string, onSuccess?: () => void) => {
    submitting.value = true
    pickerError.value = ''
    try {
      await createAlbum(albumName, targetHashes.value)
      closePicker()
      onSuccess?.()
    } catch (error) {
      pickerError.value = error instanceof Error ? error.message : 'Failed to create album'
    } finally {
      submitting.value = false
    }
  }

  return {
    pickerOpen,
    targetHashes,
    albums,
    albumsLoading,
    submitting,
    pickerError,
    openPicker,
    closePicker,
    addToExistingAlbum,
    createAlbumWithSelection,
  }
}
