<template>
  <select
    :id="id"
    :value="modelValue"
    :disabled="disabled"
    :aria-label="ariaLabel"
    :class="
      cn(
        'min-h-11 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
        props.class
      )
    "
    @change="onChange"
  >
    <slot />
  </select>
</template>

<script setup lang="ts">
import { cn } from '../../lib/utils'

const props = withDefaults(
  defineProps<{
    id?: string
    modelValue?: string
    disabled?: boolean
    ariaLabel?: string
    class?: string
  }>(),
  {
    id: undefined,
    modelValue: '',
    disabled: false,
    ariaLabel: undefined,
    class: '',
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const onChange = (event: Event) => {
  const target = event.target as HTMLSelectElement
  emit('update:modelValue', target.value)
}
</script>
