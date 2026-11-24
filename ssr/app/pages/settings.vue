<template>
  <div>
    <PageHeader
      title="Settings"
      description="Manage appearance, AI dictionary language, and account session."
    />

    <div class="max-w-3xl space-y-4">
      <SettingsSectionCard
        title="Appearance"
        description="Switch between light and dark color themes."
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="text-sm text-foreground">
            Current theme: <strong class="capitalize">{{ theme }}</strong>
          </div>
          <ThemeToggle :theme="theme" show-label @toggle="authStore.toggleTheme" />
        </div>
      </SettingsSectionCard>

      <SettingsSectionCard
        title="AI Labels & Captions Language"
        description="Select the language dictionary used when searching and inspecting photo labels and captions."
      >
        <div class="max-w-xs">
          <LanguageSelector
            id="settings-lang-select"
            :model-value="preferredLang"
            :options="SUPPORTED_LANGUAGES"
            @update:model-value="authStore.setPreferredLang"
          />
        </div>
      </SettingsSectionCard>

      <MapSettingsCard />

      <SettingsSectionCard
        title="Account"
        description="Signed-in Google identity and repository access level."
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="space-y-1">
            <p class="text-sm font-medium text-foreground">{{ userEmail || 'Signed in' }}</p>
            <div class="flex flex-wrap items-center gap-1.5">
              <Badge :variant="isAdmin ? 'default' : 'secondary'">
                {{ isAdmin ? 'Admin' : 'Allowlisted User' }}
              </Badge>
              <Badge v-if="canEditAlbums" variant="outline">Album Editor</Badge>
            </div>
          </div>

          <Button variant="outline" @click="logout">
            <LogOut class="h-4 w-4" />
            <span>Sign out</span>
          </Button>
        </div>
      </SettingsSectionCard>

      <AdminRefreshCard
        v-if="isAdmin"
        :refreshing="refreshing"
        :status-message="statusMsg"
        :error="errorMsg"
        :error-request-id="errorRequestId"
        :last-result="lastResult"
        @refresh="handleRefresh"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { LogOut } from 'lucide-vue-next'
import LanguageSelector from '../components/common/LanguageSelector.vue'
import ThemeToggle from '../components/common/ThemeToggle.vue'
import AdminRefreshCard from '../components/organisms/AdminRefreshCard.vue'
import MapSettingsCard from '../components/organisms/MapSettingsCard.vue'
import PageHeader from '../components/organisms/PageHeader.vue'
import SettingsSectionCard from '../components/organisms/SettingsSectionCard.vue'
import Badge from '../components/ui/Badge.vue'
import Button from '../components/ui/Button.vue'
import { useFirebaseAuth } from '../composables/useFirebaseAuth'
import { PhotosphereApiError, usePhotosphereApi } from '../composables/usePhotosphereApi'
import { SUPPORTED_LANGUAGES } from '../constants'
import { useAuthStore } from '../stores/auth'
import type { RefreshDatabaseResponse } from '../types'

const authStore = useAuthStore()
const { preferredLang, theme, isAdmin, canEditAlbums, userEmail } = storeToRefs(authStore)
const { logout } = useFirebaseAuth()
const { refreshDatabase } = usePhotosphereApi()

const refreshing = ref(false)
const statusMsg = ref('')
const errorMsg = ref('')
const errorRequestId = ref<string | undefined>(undefined)
const lastResult = ref<RefreshDatabaseResponse | null>(null)

const handleRefresh = async () => {
  refreshing.value = true
  statusMsg.value = ''
  errorMsg.value = ''
  errorRequestId.value = undefined
  try {
    const res = await refreshDatabase()
    lastResult.value = res
    statusMsg.value = `Refreshed ${res.totalRecords} media records and ${res.totalAlbums} albums (${res.lang}).`
  } catch (error) {
    errorMsg.value = error instanceof Error ? error.message : 'Failed to refresh remote database'
    errorRequestId.value = error instanceof PhotosphereApiError ? error.requestId : undefined
  } finally {
    refreshing.value = false
  }
}
</script>
