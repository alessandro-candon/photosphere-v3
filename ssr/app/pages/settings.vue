<template>
  <q-page class="q-pa-md">
    <HeaderPageComponent title="Settings" :subtitle="userEmail || undefined" />

    <q-card bordered flat class="q-mb-md" style="max-width: 520px">
      <q-card-section class="q-gutter-md">
        <div class="text-subtitle1">Language & Metadata</div>
        <q-select
          v-model="selectedLang"
          outlined
          dense
          emit-value
          map-options
          label="Metadata Language (labels & captions)"
          :options="languageOptions"
          @update:model-value="onChangeLang"
        />
      </q-card-section>
    </q-card>

    <q-card bordered flat style="max-width: 520px">
      <q-card-section class="q-gutter-sm">
        <div class="text-subtitle1">Administrator</div>
        <div class="text-caption text-grey-7">
          Force reload canonical JSON databases and albums from DATA bucket into memory.
        </div>
        <q-btn
          color="primary"
          icon="refresh"
          label="Refresh Remote Database"
          :loading="refreshing"
          no-caps
          @click="handleRefresh"
        />
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useQuasar } from 'quasar'
import { storeToRefs } from 'pinia'
import { SUPPORTED_LANGUAGES } from '../constants'
import { useFirebaseAuth } from '../composables/useFirebaseAuth'
import { usePhotosphereApi } from '../composables/usePhotosphereApi'
import { useAuthStore } from '../stores/auth'

const $q = useQuasar()
const authStore = useAuthStore()
const { preferredLang } = storeToRefs(authStore)
const { userEmail } = useFirebaseAuth()
const { refreshDatabase } = usePhotosphereApi()

const selectedLang = ref(preferredLang.value)
const refreshing = ref(false)
const languageOptions = SUPPORTED_LANGUAGES.map((entry) => ({
  label: entry.label,
  value: entry.code,
}))

const onChangeLang = (val: string) => {
  authStore.setPreferredLang(val)
  $q.notify({ type: 'info', message: `Language switched to ${val}` })
}

const handleRefresh = async () => {
  refreshing.value = true
  try {
    const res = await refreshDatabase()
    $q.notify({
      type: 'positive',
      message: `Reloaded ${res.totalRecords} media records and ${res.totalAlbums} albums`,
    })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error instanceof Error ? error.message : 'Database refresh failed (admin required)',
    })
  } finally {
    refreshing.value = false
  }
}
</script>
