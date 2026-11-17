export interface ParsedGsUri {
  bucket: string
  objectPath: string
}

export const parseGsUri = (gsUri: string | null | undefined): ParsedGsUri | null => {
  if (!gsUri || typeof gsUri !== 'string' || !gsUri.startsWith('gs://')) {
    return null
  }
  const withoutScheme = gsUri.slice('gs://'.length)
  const slashIndex = withoutScheme.indexOf('/')
  if (slashIndex <= 0 || slashIndex === withoutScheme.length - 1) {
    return null
  }
  const bucket = withoutScheme.slice(0, slashIndex).trim()
  const rawObjectPath = withoutScheme.slice(slashIndex + 1).replace(/^\/+/, '')
  if (!bucket || !rawObjectPath) {
    return null
  }
  const segments = rawObjectPath.split('/')
  if (segments.some((seg) => !seg || seg === '.' || seg === '..')) {
    return null
  }
  return { bucket, objectPath: rawObjectPath }
}

export const encodePathSegments = (objectPath: string): string =>
  objectPath
    .split('/')
    .map((segment) => encodeURIComponent(segment))
    .join('/')

export const toProxyUrl = (
  bucketUri: string | null | undefined,
  allowedMediaBucket?: string
): string | null => {
  const parsed = parseGsUri(bucketUri)
  if (!parsed) {
    return null
  }
  if (allowedMediaBucket && parsed.bucket !== allowedMediaBucket) {
    return null
  }
  return `/api/img/${encodePathSegments(parsed.objectPath)}`
}
