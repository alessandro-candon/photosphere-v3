import type { MediaFileType } from '../file'

export interface MediaFilterState {
  q: string
  fileType: MediaFileType | 'ALL'
  album: string
  hasLocation: boolean
  dateFrom: string
  dateTo: string
}
