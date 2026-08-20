// packages/dashboard/src/app/layout.tsx
import type { Metadata } from 'next'
import './globals.css'
import { Providers } from '@/app/providers'

export const metadata: Metadata = {
  title: 'IBCP-SCADA - Indus Basin Cyber-Physical System',
  description: 'Unified Mega System for Flood Management, Water Distribution, and Agricultural Intelligence',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}