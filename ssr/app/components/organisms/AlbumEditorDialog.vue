<template>
  <Dialog
    :open="open"
    :title="mode === 'create' ? 'Create Album' : 'Rename Album'"
    :description="
      mode === 'create' ? 'Enter a unique album name.' : 'Choose a new unique name for this album.'
    "
    @close="emit('close')"
  >
    <form class="space-y-4" @submit.prevent="onSubmit">
      <div class="space-y-1.5">
        <label for="album-name-input" class="text-xs font-medium text-muted-foreground">
          Album name
        </label>
        <Input
          id="album-name-input"
          v-model="nameInput"
          placeholder="e.g. Summer Trip 2026"
          :disabled="submitting"
        />
        <p v-if="validationError" class="text-xs text-destructive">
          {{ validationError }}
        </p>
      </div>

      <ErrorBanner v-if="error" :message="error" />

      <div class="flex flex-wrap justify-end gap-2">
        <Button variant="outline" :disabled="submitting" @click="emit('close')"> Cancel </Button>
        <Button type="submit" :disabled="submitting">
          {{ submitting ? 'Saving...' : mode === 'create' ? 'Create' : 'Save Name' }}
        </Button>
      </div>
    </form>
  </Dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import ErrorBanner from '../common/ErrorBanner.vue'
import Button from '../ui/Button.vue'
import Dialog from '../ui/Dialog.vue'
import Input from '../ui/Input.vue'

const props = withDefaults(
  defineProps<{
    open: boolean
    mode: 'create' | 'rename'
    initialName?: string
    submitting: boolean
    error: string
  }>(),
  {
    initialName: '',
  }
)

const emit = defineEmits<{
  submit: [name: string]
  close: []
}>()

const nameInput = ref(props.initialName)
const validationError = ref('')

watch(
  () => [props.open, props.initialName],
  () => {
    nameInput.value = props.initialName || ''
    validationError.value = ''
  }
)

const onSubmit = () => {
  const clean = nameInput.value.trim()
  if (!clean) {
    validationError.value = 'Album name cannot be empty.'
    return
  }
  if (clean.length > 120) {
    validationError.value = 'Album name must be 120 characters or fewer.'
    return
  }
  if (clean.includes('/') || clean.includes('\\')) {
    validationError.value = 'Album name cannot contain slashes.'
    return
  }
  validationError.value = ''
  emit('submit', clean)
}
</script>
