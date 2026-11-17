export interface LocationSearchResult {
  displayName: string
  lat: number
  lon: number
  boundingBox: [string, string, string, string] | null
}

export interface LocationSearchResponse {
  results: LocationSearchResult[]
}
