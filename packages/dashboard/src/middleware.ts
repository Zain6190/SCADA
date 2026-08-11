// packages/dashboard/src/middleware.ts
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

// We can't access sessionStorage in middleware, so check cookies or URL
// For sessionStorage, we'll redirect to login if no token
// Alternative: Use a cookie for the token too (optional)

export function middleware(request: NextRequest) {
  // Check if token exists in session (client-side)
  // Middleware runs on server, so we can't access sessionStorage
  // Instead, redirect to login if accessing protected route
  const { pathname } = request.nextUrl

  // Public paths
  const publicPaths = ['/login', '/register', '/', '/api/auth']
  const isPublic = publicPaths.some(path => pathname.startsWith(path))

  // For protected routes, we'll check on client-side
  // The server middleware just passes through
  // Auth check happens in the component with useAuth()

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)']
}