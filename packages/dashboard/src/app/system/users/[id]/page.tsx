// packages/dashboard/src/app/system/users/[id]/page.tsx
// Static export requires generateStaticParams here; the interactive UI is a client component.
import { UserDetailClient } from './client'

export function generateStaticParams() {
  return Array.from({ length: 50 }, (_, i) => ({ id: String(i + 1) }))
}

export default function UserDetailPage() {
  return <UserDetailClient />
}