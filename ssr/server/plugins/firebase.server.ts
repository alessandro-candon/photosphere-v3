import { defineNitroPlugin } from 'nitropack/runtime'
import { ensureFirebaseAdminInitialized } from '../services/firebase-admin.service'

export default defineNitroPlugin(() => {
  ensureFirebaseAdminInitialized()
})
