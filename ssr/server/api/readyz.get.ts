import { accessSync, constants } from 'node:fs'
import { createError, defineEventHandler } from 'h3'
import { useRuntimeConfig } from '#imports'
import { ensureMountedVolumeDir } from '../utils/storage-download'

export default defineEventHandler((event) => {
  const cfg = useRuntimeConfig(event)
  const mediaBucket = cfg.storage?.mediaBucket || ''
  const dataBucket = cfg.storage?.dataBucket || ''
  const mountedVolumePath = cfg.storage?.mountedVolumePath || '/mnt/photosphere'

  if (!mediaBucket || !dataBucket) {
    throw createError({
      statusCode: 503,
      statusMessage: 'Service Unavailable: Media or data bucket is not configured',
    })
  }

  try {
    const dir = ensureMountedVolumeDir(undefined, mountedVolumePath)
    accessSync(dir, constants.R_OK | constants.W_OK)
  } catch {
    throw createError({
      statusCode: 503,
      statusMessage: 'Service Unavailable: Mounted cache volume is not writable',
    })
  }

  return {
    status: 'ready',
    mediaBucket,
    dataBucket,
    mountedVolumePath,
  }
})
