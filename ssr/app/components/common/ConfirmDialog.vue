<template>
  <Dialog :open="open" :title="title" :description="description" @close="emit('cancel')">
    <div class="mt-4 flex flex-wrap justify-end gap-2">
      <Button variant="outline" :disabled="submitting" @click="emit('cancel')"> Cancel </Button>
      <Button
        :variant="destructive ? 'destructive' : 'default'"
        :disabled="submitting"
        @click="emit('confirm')"
      >
        {{ submitting ? 'Working...' : confirmLabel }}
      </Button>
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import Button from '../ui/Button.vue'
import Dialog from '../ui/Dialog.vue'

withDefaults(
  defineProps<{
    open: boolean
    title: string
    description?: string
    confirmLabel?: string
    destructive?: boolean
    submitting?: boolean
  }>(),
  {
    description: undefined,
    confirmLabel: 'Confirm',
    destructive: false,
    submitting: false,
  }
)

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()
</script>
