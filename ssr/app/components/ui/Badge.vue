<template>
  <span :class="classes">
    <slot />
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '../../lib/utils'

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground',
        secondary: 'bg-muted text-foreground',
        outline: 'border border-border bg-surface text-muted-foreground',
        destructive: 'bg-destructive/15 text-destructive border border-destructive/30',
      },
    },
    defaultVariants: {
      variant: 'secondary',
    },
  }
)

type BadgeVariants = VariantProps<typeof badgeVariants>

const props = withDefaults(
  defineProps<{
    variant?: BadgeVariants['variant']
    class?: string
  }>(),
  {
    variant: 'secondary',
    class: '',
  }
)

const classes = computed(() => cn(badgeVariants({ variant: props.variant }), props.class))
</script>
