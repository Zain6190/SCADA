import type { SVGProps } from 'react'

/** River tributaries and telemetry stations converging into one operational view. */
export function BrandMark(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 64 64" width="32" height="32" fill="none" aria-hidden="true" focusable="false" {...props}>
      <path d="M25 13v6c0 10 14 10 14 20S25 48 25 53M47 16v4c0 8-8 11-14 11M13 32h6c8 0 11 7 20 7" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      <g fill="currentColor">
        <circle cx="25" cy="13" r="4" />
        <circle cx="47" cy="16" r="4" />
        <circle cx="13" cy="32" r="4" />
      </g>
    </svg>
  )
}
