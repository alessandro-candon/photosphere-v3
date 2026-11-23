<template>
  <DialogRoot :open="open" @update:open="onOpenChange">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-50 bg-scrim backdrop-blur-xs" />
      <DialogContent :class="contentClasses">
        <div class="flex items-start justify-between gap-3 border-b border-border pb-3">
          <div>
            <DialogTitle class="text-base font-semibold tracking-tight">
              {{ title }}
            </DialogTitle>
            <DialogDescription v-if="description" class="mt-1 text-xs text-muted-foreground">
              {{ description }}
            </DialogDescription>
            <DialogDescription v-else class="sr-only">
              {{ title }}
            </DialogDescription>
          </div>
          <DialogClose as-child>
            <button
              type="button"
              aria-label="Close sheet"
              class="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X class="h-4 w-4" />
            </button>
          </DialogClose>
        </div>

        <div class="mt-4 overflow-y-auto">
          <slot />
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<script setup lang="ts">
import { computed } from 'vue'
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
    side?: 'bottom' | 'right'
    class?: string
  }>(),
  {
    description: undefined,
    side: 'bottom',
    class: '',
  }
)

const emit = defineEmits<{
  close: []
}>()

const contentClasses = computed(() =>
  cn(
    'fixed z-50 flex flex-col border border-border bg-surface-elevated p-5 text-foreground shadow-xl focus:outline-none',
    props.side === 'right'
      ? 'inset-y-0 right-0 w-full max-w-md border-l rounded-none sm:rounded-l-xl'
      : 'inset-x-0 bottom-0 max-h-[85vh] rounded-t-2xl border-t md:left-1/2 md:top-1/2 md:bottom-auto md:w-full md:max-w-lg md:-translate-x-1/2 md:-translate-y-1/2 md:rounded-xl md:border',
    props.class
  )
)

const onOpenChange = (nextOpen: boolean) => {
  if (!nextOpen) {
    emit('close')
  }
}
</script>
