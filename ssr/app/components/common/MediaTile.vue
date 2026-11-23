<template>
  <div
    :class="[
      'group relative h-full w-full overflow-hidden rounded-sm bg-muted transition-all cursor-pointer select-none',
      selected ? 'ring-3 ring-primary ring-offset-2 ring-offset-background' : '',
    ]"
    role="button"
    tabindex="0"
    :aria-label="selecting ? `Select ${item.fileName}` : `Open ${item.fileName}`"
    @click="onMainClick"
    @keydown.enter.prevent="onMainClick"
    @keydown.space.prevent="onMainClick"
  >
    <img
      v-if="item.hasThumbnail && item.thumbnailUrl && !imgFailed"
      :src="item.thumbnailUrl"
      :alt="item.fileName"
      loading="lazy"
      class="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.02]"
      @error="imgFailed = true"
    />

    <div
      v-else
      class="flex h-full w-full flex-col items-center justify-center gap-1.5 bg-muted p-2 text-muted-foreground"
    >
      <Film v-if="item.fileType === 'VIDEO'" class="h-7 w-7" />
      <FileText v-else-if="item.fileType === 'FILE'" class="h-7 w-7" />
      <ImageOff v-else class="h-7 w-7" />
      <span class="max-w-full truncate px-1 text-[11px]">{{ item.fileName }}</span>
    </div>

    <!-- Selection checkbox (44x44 touch target) -->
    <button
      v-if="showSelectControl"
      type="button"
      :aria-label="selected ? `Deselect ${item.fileName}` : `Select ${item.fileName}`"
      :aria-pressed="selected"
      :class="[
        'absolute left-0 top-0 z-10 flex min-h-11 min-w-11 items-start justify-start p-2 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        selecting || selected
          ? 'opacity-100'
          : 'opacity-100 md:opacity-0 md:group-hover:opacity-100 focus-visible:opacity-100',
      ]"
      @click.stop="emit('toggle-select', item.hash)"
    >
      <span
        :class="[
          'flex h-6 w-6 items-center justify-center rounded-full border shadow-sm transition-colors',
          selected
            ? 'border-primary bg-primary text-primary-foreground'
            : 'border-white/80 bg-black/45 text-white',
        ]"
      >
        <Check v-if="selected" class="h-3.5 w-3.5" />
      </span>
    </button>

    <!-- File type indicator for video/file -->
    <div
      v-if="item.fileType !== 'IMAGE'"
      class="pointer-events-none absolute bottom-2 right-2 flex items-center gap-1 rounded-full bg-black/65 px-2 py-0.5 text-[11px] font-medium text-white backdrop-blur-xs"
    >
      <Video v-if="item.fileType === 'VIDEO'" class="h-3 w-3" />
      <FileText v-else class="h-3 w-3" />
      <span>{{ item.fileType === 'VIDEO' ? 'Video' : 'File' }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Check, FileText, Film, ImageOff, Video } from 'lucide-vue-next'
import type { MediaGridItem } from '../../types'

const props = withDefaults(
  defineProps<{
    item: MediaGridItem
    selected: boolean
    selecting: boolean
    showSelectControl?: boolean
  }>(),
  {
    showSelectControl: true,
  }
)

const emit = defineEmits<{
  open: [item: MediaGridItem]
  'toggle-select': [hash: string]
}>()

const imgFailed = ref(false)

watch(
  () => props.item.thumbnailUrl,
  () => {
    imgFailed.value = false
  }
)

const onMainClick = () => {
  if (props.selecting) {
    emit('toggle-select', props.item.hash)
  } else {
    emit('open', props.item)
  }
}
</script>
