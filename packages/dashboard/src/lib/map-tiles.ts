// packages/dashboard/src/lib/map-tiles.ts
// Keyless Esri gray-canvas basemaps. Carto's keyless tier was retired and
// now serves "API KEY REQUIRED" error tiles instead of map imagery.
// Esri's tile template is {z}/{y}/{x} (y before x), and the canvas layers
// stop at zoom 16, so callers must pass maxZoom accordingly.

export const DARK_GRAY_TILES =
  'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}'

export const LIGHT_GRAY_TILES =
  'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}'

export const GRAY_TILES_MAX_ZOOM = 16

export const DARK_GRAY_ATTRIBUTION =
  '&copy; <a href="https://www.esri.com/">Esri</a>, HERE, Garmin, NOAA, USGS, NGA'

export const LIGHT_GRAY_ATTRIBUTION =
  '&copy; <a href="https://www.esri.com/">Esri</a>, HERE, Garmin, NOAA, USGS, NGA'
