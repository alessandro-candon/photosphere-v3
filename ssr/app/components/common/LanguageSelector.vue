<template>
  <Select
    :id="id"
    :model-value="modelValue"
    :disabled="disabled"
    aria-label="AI labels and captions language"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <option v-for="entry in options" :key="entry.code" :value="entry.code">
      {{ entry.label }} ({{ entry.code }})
    </option>
  </Select>
</template>

<script setup lang="ts">
import Select from '../ui/Select.vue'

withDefaults(
  defineProps<{
    id?: string
    modelValue: string
    options: readonly { code: string; label: string }[]
    disabled?: boolean
  }>(),
  {
    id: undefined,
    disabled: false,
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>
