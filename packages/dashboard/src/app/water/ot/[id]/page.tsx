import { OtDeviceClient } from './client'

export function generateStaticParams() {
  return Array.from({ length: 16 }, (_, i) => ({ id: String(i + 1) }))
}

export default function OtDevicePage() {
  return <OtDeviceClient />
}
