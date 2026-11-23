<template>
  <section
    :class="cn('rounded-xl border border-border bg-surface text-foreground shadow-sm', props.class)"
  >
    <slot />
  </section>
</template>

<script setup lang="ts">
import { cn } from '../../lib/utils'

const props = withDefaults(
  defineProps<{
    class?: string
  }>(),
  {
    class: '',
  }
)
</script>
