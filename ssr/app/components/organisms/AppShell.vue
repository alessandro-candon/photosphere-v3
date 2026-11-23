<template>
  <div class="min-h-screen bg-background text-foreground">
    <template v-if="authenticated">
      <!-- Desktop left navigation rail -->
      <aside
        class="hidden md:fixed md:inset-y-0 md:left-0 md:z-30 md:flex md:w-20 lg:w-56 md:flex-col border-r border-border bg-surface"
        aria-label="Primary navigation"
      >
        <div class="flex h-16 items-center gap-2.5 border-b border-border px-4">
          <NuxtLink
            to="/"
            class="flex items-center gap-2.5 text-foreground no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-lg"
          >
            <span
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground"
            >
              <Camera class="h-5 w-5" />
            </span>
            <span class="hidden lg:inline text-base font-semibold tracking-tight">Photosphere</span>
          </NuxtLink>
        </div>

        <nav class="flex flex-1 flex-col gap-1 p-2.5">
          <NuxtLink
            v-for="item in navItems"
            :key="item.to"
            :to="item.to"
            :class="[
              'flex min-h-11 items-center justify-center lg:justify-start gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              isRouteActive(item.to)
                ? 'bg-primary/12 text-primary'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground',
            ]"
          >
            <component :is="item.icon" class="h-5 w-5 shrink-0" />
            <span class="hidden lg:inline">{{ item.label }}</span>
          </NuxtLink>
        </nav>

        <div class="border-t border-border p-2.5 space-y-2">
          <div v-if="userEmail" class="hidden lg:block truncate px-2 text-xs text-muted-foreground">
            {{ userEmail }}
          </div>
          <div class="flex flex-col lg:flex-row items-center justify-between gap-1.5">
            <ThemeToggle :theme="theme" @toggle="emit('toggle-theme')" />
            <Button variant="ghost" size="icon" aria-label="Sign out" @click="emit('logout')">
              <LogOut class="h-4 w-4" />
            </Button>
          </div>
        </div>
      </aside>

      <!-- Mobile sticky top bar -->
      <header
        class="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-surface/95 px-3 backdrop-blur-sm md:hidden"
      >
        <NuxtLink to="/" class="flex items-center gap-2 text-foreground no-underline">
          <span
            class="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground"
          >
            <Camera class="h-4 w-4" />
          </span>
          <span class="text-base font-semibold tracking-tight">Photosphere</span>
        </NuxtLink>

        <div class="flex items-center gap-1">
          <ThemeToggle :theme="theme" @toggle="emit('toggle-theme')" />
          <Button variant="ghost" size="icon" aria-label="Sign out" @click="emit('logout')">
            <LogOut class="h-4 w-4" />
          </Button>
        </div>
      </header>

      <!-- Main content -->
      <main class="pb-20 md:pb-8 md:pl-20 lg:pl-56">
        <div class="mx-auto w-full max-w-[1600px] px-3 py-4 md:px-6 md:py-5">
          <slot />
        </div>
      </main>

      <!-- Mobile fixed bottom navigation bar -->
      <nav
        class="fixed inset-x-0 bottom-0 z-30 flex h-16 items-center justify-around border-t border-border bg-surface/95 backdrop-blur-sm md:hidden"
        aria-label="Mobile navigation"
      >
        <NuxtLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          :class="[
            'flex min-h-11 min-w-14 flex-col items-center justify-center gap-0.5 rounded-lg px-2 py-1 text-[11px] font-medium transition-colors',
            isRouteActive(item.to) ? 'text-primary' : 'text-muted-foreground hover:text-foreground',
          ]"
        >
          <component :is="item.icon" class="h-5 w-5" />
          <span>{{ item.label }}</span>
        </NuxtLink>
      </nav>
    </template>

    <!-- Unauthenticated shell (e.g. /login) -->
    <template v-else>
      <div class="fixed right-4 top-4 z-30">
        <ThemeToggle :theme="theme" @toggle="emit('toggle-theme')" />
      </div>
      <main class="min-h-screen px-4 py-8">
        <slot />
      </main>
    </template>
  </div>
</template>

<script setup lang="ts">
import { Camera, FolderHeart, Images, LogOut, Settings, Sparkles } from 'lucide-vue-next'
import ThemeToggle from '../common/ThemeToggle.vue'
import Button from '../ui/Button.vue'

const props = defineProps<{
  authenticated: boolean
  userEmail: string | null
  currentPath: string
  theme: 'light' | 'dark'
}>()

const emit = defineEmits<{
  logout: []
  'toggle-theme': []
}>()

const navItems = [
  { to: '/', label: 'Photos', icon: Images },
  { to: '/memories', label: 'Memories', icon: Sparkles },
  { to: '/albums', label: 'Albums', icon: FolderHeart },
  { to: '/settings', label: 'Settings', icon: Settings },
] as const

const isRouteActive = (target: string): boolean => {
  if (target === '/') {
    return props.currentPath === '/'
  }
  return props.currentPath === target || props.currentPath.startsWith(`${target}/`)
}
</script>
