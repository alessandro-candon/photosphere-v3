import { effectScope, ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useMediaFeed } from '../../app/composables/useMediaFeed'
import { useMediaLightbox } from '../../app/composables/useMediaLightbox'
import { useAuthStore } from '../../app/stores/auth'
import type { GalleryFilters, MediaGridItem } from '../../app/types'
import {
  formatCompactDate,
  formatMediaDateTime,
  formatTimelineDateGroup,
  formatUtcMonthDay,
  toEpochMilliseconds,
} from '../../shared'
import { setMockNuxtApp } from '../nuxt-imports-stub'

const makeGridItem = (idx: number): MediaGridItem => ({
  hash: idx.toString(16).padStart(40, '0'),
  fileType: 'IMAGE',
  createdAt: '2024-05-09T10:00:00Z',
  createdAtTimestamp: 1715248800 + idx,
  fileName: `IMG_${idx}.jpg`,
  hasThumbnail: true,
  thumbnailUrl: `/api/media/${idx.toString(16).padStart(40, '0')}?variant=thumbnail`,
  sourceUrl: `/api/media/${idx.toString(16).padStart(40, '0')}?variant=source`,
  latitude: 45.4642,
  longitude: 9.19,
  geohash: 'u0nd9h',
})

describe('Shared Date Helpers, useMediaFeed Race Cancellation & useMediaLightbox', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    setActivePinia(createPinia())
    setMockNuxtApp({})
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('formats timestamps consistently across timeline, lightbox, and inspector modes', () => {
    expect(toEpochMilliseconds(1715248800)).toBe(1715248800000)
    expect(toEpochMilliseconds(1715248800000)).toBe(1715248800000)
    expect(formatUtcMonthDay(1715248800)).toBe('05-09')
    expect(formatTimelineDateGroup(null)).toBe('Undated')
    expect(formatMediaDateTime(null, null)).toBe('')
    expect(formatMediaDateTime(null, '2024-05-09')).toBe('2024-05-09')
    expect(formatCompactDate(null)).toBe('Unknown date')
  })

  it('cancels stale loadInitial requests via AbortController without clobbering loading state', async () => {
    const authStore = useAuthStore()
    authStore.setSession(
      { uid: 'u1', email: 'u@example.com', displayName: null, photoURL: null },
      'tok'
    )
    authStore.setInitialized(true)

    const filters = ref<GalleryFilters>({})
    let callCount = 0
    let resolveSecond!: (res: Response) => void

    globalThis.fetch = vi.fn((_url: string | URL | Request, init?: RequestInit) => {
      callCount += 1
      if (callCount === 1) {
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'))
          })
        })
      }
      return new Promise<Response>((resolve) => {
        resolveSecond = resolve
      })
    }) as unknown as typeof fetch

    const feed = useMediaFeed(() => filters.value, 20)
    expect(feed.loading.value).toBe(true)

    // Trigger filter change while first request is still pending
    filters.value = { fileType: 'IMAGE' }
    await Promise.resolve()
    await Promise.resolve()

    // First request aborted, but second is still pending so loading must stay true
    expect(feed.loading.value).toBe(true)

    resolveSecond(
      new Response(
        JSON.stringify({
          items: [makeGridItem(2)],
          totalCount: 1,
          page: 1,
          limit: 20,
          hasMore: false,
        }),
        { status: 200 }
      )
    )
    await new Promise((r) => setTimeout(r, 10))
    expect(feed.loading.value).toBe(false)
    expect(feed.items.value.map((i) => i.fileName)).toEqual(['IMG_2.jpg'])
  })

  it('caches MediaDetail by hash, invalidates on language change, and auto-paginates on nextItem', async () => {
    const authStore = useAuthStore()
    authStore.setSession(
      { uid: 'u1', email: 'u@example.com', displayName: null, photoURL: null },
      'tok'
    )

    const items = ref<MediaGridItem[]>([makeGridItem(1)])
    const hasMore = ref(true)
    const loadMore = vi.fn(async () => {
      items.value.push(makeGridItem(2))
      hasMore.value = false
    })

    const detailFetchMock = vi.fn(async (url: string | URL | Request) => {
      const target = String(url)
      const isIt = target.includes('lang=it')
      return new Response(
        JSON.stringify({
          ...makeGridItem(target.includes('0002') ? 2 : 1),
          labels: [isIt ? 'cane' : 'dog'],
          caption: isIt ? 'Un cane' : 'A dog',
        }),
        { status: 200 }
      )
    }) as unknown as typeof fetch
    globalThis.fetch = detailFetchMock

    const lightbox = useMediaLightbox({ items, hasMore, loadMore })
    await lightbox.openLightbox(0)
    expect(lightbox.activeDetail.value?.labels).toEqual(['dog'])
    expect(detailFetchMock).toHaveBeenCalledTimes(1)

    // Re-opening item 0 uses cached detail
    await lightbox.nextItem()
    expect(loadMore).toHaveBeenCalledTimes(1)
    expect(lightbox.activeItem.value?.fileName).toBe('IMG_2.jpg')
    await lightbox.prevItem()
    expect(detailFetchMock).toHaveBeenCalledTimes(2)

    // Changing language clears detailCache and re-fetches active item
    authStore.setPreferredLang('it')
    await new Promise((r) => setTimeout(r, 10))
    expect(lightbox.activeDetail.value?.labels).toEqual(['cane'])
    expect(detailFetchMock).toHaveBeenCalledTimes(3)
  })
})
