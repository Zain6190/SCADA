// packages/dashboard/src/features/water/rivers.ts
// Real-world approximate river geometry for Pakistan's major rivers.
// Coordinates: [lat, lng] pairs along the approximate river path.

export interface RiverPath {
  name: string
  color: string
  weight: number
  paths: [number, number][][]
}

// Indus River: Tarbela → Kalabagh → Chashma → Taunsa → Guddu → Sukkur → Kotri → Sea
const INDUS_PATH: [number, number][] = [
  [34.086, 72.716],  // Tarbela Dam
  [33.95, 72.68],
  [33.80, 72.55],
  [33.60, 72.40],
  [33.40, 72.25],
  [33.20, 72.10],
  [33.00, 71.80],
  [32.960, 71.490],  // Kalabagh
  [32.80, 71.45],
  [32.65, 71.42],
  [32.485, 71.480],  // Chashma
  [32.30, 71.40],
  [32.10, 71.30],
  [31.90, 71.20],
  [31.70, 71.10],
  [31.50, 71.00],
  [31.30, 70.95],
  [31.10, 70.90],
  [30.805, 70.880],  // Taunsa
  [30.60, 70.80],
  [30.40, 70.70],
  [30.20, 70.55],
  [30.00, 70.40],
  [29.80, 70.20],
  [29.60, 70.00],
  [29.40, 69.85],
  [29.20, 69.70],
  [29.00, 69.55],
  [28.80, 69.40],
  [28.60, 69.20],
  [28.430, 68.940],  // Guddu
  [28.30, 68.85],
  [28.10, 68.75],
  [27.90, 68.65],
  [27.690, 68.410],  // Sukkur
  [27.50, 68.38],
  [27.30, 68.36],
  [27.10, 68.35],
  [26.90, 68.34],
  [26.70, 68.34],
  [26.50, 68.34],
  [26.30, 68.34],
  [26.10, 68.34],
  [25.90, 68.34],
  [25.70, 68.34],
  [25.50, 68.34],
  [25.370, 68.350],  // Kotri
  [25.20, 68.36],
  [25.00, 68.38],
  [24.80, 68.40],
  [24.60, 67.30],
  [24.50, 67.00],
  [24.40, 66.80],
]

// Jhelum River: Mangla → confluence with Chenab near Trimmu
const JHELUM_PATH: [number, number][] = [
  [33.215, 73.640],  // Mangla Dam
  [33.05, 73.55],
  [32.90, 73.40],
  [32.75, 73.25],
  [32.60, 73.10],
  [32.50, 72.95],
  [32.40, 72.80],
  [32.35, 72.65],
  [32.30, 72.50],
  [32.25, 72.35],
  [32.20, 72.20],
  [32.15, 72.00],
  [32.10, 71.85],
  [32.05, 71.70],
  [32.00, 71.55],
]

// Kabul River: Afghanistan → Nowshera → confluence with Indus near Attock
const KABUL_PATH: [number, number][] = [
  [34.50, 71.00],  // Afghanistan border
  [34.40, 71.15],
  [34.30, 71.30],
  [34.20, 71.42],
  [34.10, 71.50],
  [34.010, 71.580],  // Nowshera
  [33.95, 71.65],
  [33.90, 71.72],
  [33.85, 71.80],
  [33.80, 71.90],
  [33.75, 72.00],
  [33.70, 72.10],
  [33.65, 72.25],
  [33.60, 72.40],
  [33.55, 72.55],
]

// Chenab River: Marala → through Punjab → confluence with Jhelum
const CHENAB_PATH: [number, number][] = [
  [32.480, 74.560],  // Marala Headworks
  [32.42, 74.40],
  [32.35, 74.25],
  [32.28, 74.10],
  [32.20, 73.95],
  [32.12, 73.80],
  [32.05, 73.65],
  [31.98, 73.50],
  [31.90, 73.35],
  [31.85, 73.20],
  [31.80, 73.05],
  [31.75, 72.90],
  [31.70, 72.75],
  [31.65, 72.60],
  [31.60, 72.45],
  [31.55, 72.30],
  [31.50, 72.15],
]

// Panjnad: confluence → joins Indus near Panjnad Headworks
const PANJNAD_PATH: [number, number][] = [
  [31.30, 72.10],  // Confluence area (Jhelum+Chenab)
  [31.10, 71.90],
  [30.90, 71.70],
  [30.70, 71.50],
  [30.50, 71.30],
  [30.30, 71.10],
  [30.10, 70.95],
  [29.90, 70.80],
  [29.70, 70.60],
  [29.50, 70.40],
  [29.30, 70.20],
  [29.10, 70.00],
  [28.90, 69.85],
  [28.70, 69.75],
  [28.50, 69.70],
  [28.400, 69.700],  // Panjnad Headworks
]

export const RIVER_GEOMETRY: RiverPath[] = [
  { name: 'Indus', color: '#38bdf8', weight: 4, paths: [INDUS_PATH] },
  { name: 'Jhelum', color: '#34d399', weight: 3, paths: [JHELUM_PATH] },
  { name: 'Kabul', color: '#f59e0b', weight: 3, paths: [KABUL_PATH] },
  { name: 'Chenab', color: '#a78bfa', weight: 3, paths: [CHENAB_PATH] },
  { name: 'Panjnad', color: '#f472b6', weight: 2, paths: [PANJNAD_PATH] },
]

// River segment lookup: from_asset → to_asset → river name
export const SEGMENT_RIVER: Record<string, string> = {
  '1-4': 'Indus',
  '4-3': 'Indus',
  '3-5': 'Indus',
  '5-6': 'Indus',
  '6-7': 'Indus',
  '7-8': 'Indus',
  '2-3': 'Jhelum',
  '9-4': 'Kabul',
  '10-3': 'Chenab',
  '11-6': 'Panjnad',
}
