// packages/dashboard/src/lib/config.ts
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://127.0.0.1:8000/api/v1'

export const PKT_OFFSET_MS = 5 * 60 * 60 * 1000

export const REFRESH_INTERVAL = 60_000