// packages/dashboard/src/app/water/alerts/page.tsx
// Redirect to the operational alerts page.
'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function AlertsRedirect() {
  const router = useRouter()
  useEffect(() => {
    router.replace('/water/operator/alerts')
  }, [router])
  return null
}
