import type * as Leaflet from 'leaflet'

declare module 'leaflet' {
  type HeatLatLngTuple = [number, number, number?]

  interface HeatMapOptions {
    minOpacity?: number
    maxZoom?: number
    max?: number
    radius?: number
    blur?: number
    gradient?: Record<number, string>
  }

  interface HeatLayer extends Leaflet.Layer {
    setOptions(options: HeatMapOptions): this
    addLatLng(latlng: Leaflet.LatLng | HeatLatLngTuple): this
    setLatLngs(latlngs: Array<Leaflet.LatLng | HeatLatLngTuple>): this
    redraw(): this
  }

  function heatLayer(
    latlngs: Array<Leaflet.LatLng | HeatLatLngTuple>,
    options?: HeatMapOptions
  ): HeatLayer
}
