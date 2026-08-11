'use client'

// packages/dashboard/src/components/shell/system-status.tsx
import { useQuery } from '@tanstack/react-query'
import { API_BASE_URL } from '@/lib/config'
import { cn } from '@/lib/utils'
import { Activity } from 'lucide-react'
import { useState } from 'react'

export function SystemStatusIndicator() {
  const [enabled, setEnabled] = useState(true)
  const { isPending, isError } = useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const start = Date.now()
      try {
        const res = await fetch(`${API_BASE_URL}/health`)
        if (!res.ok) throw new Error('bad status')
        return { ok: true, ms: Date.now() - start }
      } catch {
        setEnabled(false)
        throw new Error('offline')
      }
    },
    enabled,
    refetchInterval: 30_000,
    retry: 0,
  })

  return (
    <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-1.5">
      <Activity
        className={cn(
          'h-4 w-4',
          isError ? 'text-red-400' : isPending ? 'text-slate-500' : 'text-emerald-400'
        )}
      />
      <span
        className={cn(
          'text-xs font-medium',
          isError ? 'text-red-300' : isPending ? 'text-slate-400' : 'text-emerald-300'
        )}
      >
        {isError ? 'Offline' : isPending ? '…' : 'Backend Online'}
      </span>
    </div>
  )
}