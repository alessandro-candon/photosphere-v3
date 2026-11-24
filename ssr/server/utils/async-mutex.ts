export type AsyncMutex = <T>(fn: () => Promise<T>) => Promise<T>

/**
 * Creates a FIFO async mutex that serializes execution of critical sections.
 */
export const createAsyncMutex = (): AsyncMutex => {
  let queue: Promise<void> = Promise.resolve()
  return async <T>(fn: () => Promise<T>): Promise<T> => {
    const prev = queue
    let release!: () => void
    queue = new Promise<void>((resolveLock) => {
      release = resolveLock
    })
    await prev
    try {
      return await fn()
    } finally {
      release()
    }
  }
}

export interface SingleFlight<K, V> {
  run: (key: K, fn: () => Promise<V>) => Promise<V>
  clear: () => void
}

/**
 * Coalesces concurrent async operations sharing the same key.
 * Always removes the key on settlement or rejection so transient errors do not poison future calls.
 */
export const createSingleFlight = <K, V>(): SingleFlight<K, V> => {
  const inFlight = new Map<K, Promise<V>>()

  const run = (key: K, fn: () => Promise<V>): Promise<V> => {
    const existing = inFlight.get(key)
    if (existing) {
      return existing
    }
    const promise = fn().finally(() => {
      if (inFlight.get(key) === promise) {
        inFlight.delete(key)
      }
    })
    inFlight.set(key, promise)
    return promise
  }

  const clear = (): void => {
    inFlight.clear()
  }

  return { run, clear }
}
