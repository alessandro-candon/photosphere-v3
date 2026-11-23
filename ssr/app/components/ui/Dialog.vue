<template>
  <DialogRoot :open="open" @update:open="onOpenChange">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-50 bg-scrim backdrop-blur-xs" />
      <DialogContent
        :class="
          cn(
            'fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface-elevated p-5 text-foreground shadow-xl focus:outline-none',
            props.class
          )
        "
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <DialogTitle class="text-base font-semibold tracking-tight">
              {{ title }}
            </DialogTitle>
            <DialogDescription v-if="description" class="mt-1 text-sm text-muted-foreground">
              {{ description }}
            </DialogDescription>
            <DialogDescription v-else class="sr-only">
              {{ title }}
            </DialogDescription>
          </div>
          <DialogClose as-child>
            <button
              type="button"
              aria-label="Close dialog"
              class="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X class="h-4 w-4" />
            </button>
          </DialogClose>
        </div>

        <div class="mt-4">
          <slot />
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<script setup lang="ts">
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from 'reka-ui'
import { X } from 'lucide-vue-next'
import { cn } from '../../lib/utils'

const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    description?: string
    class?: string
  }>(),
  {
    description: undefined,
    class: '',
  }
)

const emit = defineEmits<{
  close: []
}>()

const onOpenChange = (nextOpen: boolean) => {
  if (!nextOpen) {
    emit('close')
  }
}
</script>
