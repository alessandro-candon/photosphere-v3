<template>
  <q-layout view="hHh lpR fFf" class="bg-grey-1">
    <q-header v-if="isAuthenticated" elevated class="bg-primary text-white">
      <q-toolbar>
        <q-btn flat dense no-caps icon="photo_library" label="Photosphere v3" to="/" />
        <q-space />
        <q-btn flat dense no-caps icon="collections" label="Albums" to="/albums" />
        <q-btn flat dense no-caps icon="history" label="Memories" to="/memories" />
        <q-btn flat dense no-caps icon="settings" label="Settings" to="/settings" />
        <q-btn flat dense no-caps icon="logout" label="Logout" @click="logout" />
      </q-toolbar>
    </q-header>

    <q-page-container>
      <slot />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { useFirebaseAuth } from '../composables/useFirebaseAuth'

const { isAuthenticated, logout } = useFirebaseAuth()
</script>
