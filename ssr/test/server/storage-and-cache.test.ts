import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { downloadDataFile, loadJsonDatabase } from '../../server/utils/storage-download'

describe('Data Bucket Storage Downloads & Local JSON Cache', () => {
  const tempDirs: string[] = []

  afterEach(() => {
    for (const dir of tempDirs.splice(0)) {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  it('downloads JSON from dataBucket with Bearer auth and caches atomically on disk', async () => {
    const vol = mkdtempSync(resolve(tmpdir(), 'ps-store-'))
    tempDirs.push(vol)

    const fetchMock = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      expect(init?.headers).toMatchObject({ Authorization: 'Bearer id-tok' })
      return new Response('{"0":"cat"}', { status: 200 })
    }) as unknown as typeof fetch

    const first = await loadJsonDatabase(
      'en_labels.json',
      'en_labels.json',
      'id-tok',
      (parsed) => parsed as Record<string, string>,
      {
        dataBucket: 'std-data-bkt',
        mountedVolumePath: vol,
        fetchImpl: fetchMock,
      }
    )
    expect(first).toEqual({ '0': 'cat' })
    expect(existsSync(resolve(vol, 'en_labels.json'))).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(1)

    // Subsequent read hits local disk cache without hitting upstream
    const second = await loadJsonDatabase(
      'en_labels.json',
      'en_labels.json',
      'id-tok',
      (parsed) => parsed as Record<string, string>,
      {
        dataBucket: 'std-data-bkt',
        mountedVolumePath: vol,
        fetchImpl: fetchMock,
      }
    )
    expect(second).toEqual({ '0': 'cat' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('handles missing bucket, upstream errors, corrupted disk cache, and emulator URLs', async () => {
    await expect(
      downloadDataFile('db.json', 'tok', {
        dataBucket: '',
        fetchImpl: vi.fn() as unknown as typeof fetch,
      })
    ).rejects.toMatchObject({ statusCode: 500 })

    const errFetch = vi.fn(
      async () => new Response('fail', { status: 500 })
    ) as unknown as typeof fetch
    await expect(
      downloadDataFile('db.json', 'tok', { dataBucket: 'data-bkt', fetchImpl: errFetch })
    ).rejects.toMatchObject({ statusCode: 502 })

    const vol = mkdtempSync(resolve(tmpdir(), 'ps-corrupt-'))
    tempDirs.push(vol)
    writeFileSync(resolve(vol, 'broken.json'), '{not-valid-json')
    await expect(
      loadJsonDatabase('broken.json', 'broken.json', 'tok', (v) => v, {
        dataBucket: 'data-bkt',
        mountedVolumePath: vol,
      })
    ).rejects.toMatchObject({ statusCode: 500 })

    process.env.STORAGE_EMULATOR_HOST = 'http://127.0.0.1:4443/'
    try {
      const emuFetch = vi.fn(
        async () => new Response('ok', { status: 200 })
      ) as unknown as typeof fetch
      await downloadDataFile('db.json', 'tok', { dataBucket: 'data-bkt', fetchImpl: emuFetch })
      expect(emuFetch).toHaveBeenCalledWith(
        expect.stringContaining('http://127.0.0.1:4443/storage/v1/b/data-bkt/o/db.json'),
        expect.any(Object)
      )
    } finally {
      delete process.env.STORAGE_EMULATOR_HOST
    }
  })
})
