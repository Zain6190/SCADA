// packages/dashboard/tailwind.config.js
// Semantic theme for IBCP-SCADA. Values live in src/app/globals.css as RGB
// triplets; this file only gives them names. Components use the names
// (bg-surface, text-ink-muted, border-line, bg-crit) — never bg-slate-900.
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    // src/lib holds class maps (severity, navigation accents) that the old
    // globs missed, so those classes were never generated.
    './src/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        canvas: token('canvas'),
        surface: {
          DEFAULT: token('surface'),
          alt: token('surface-alt'),
          sunken: token('surface-sunken'),
        },
        line: {
          DEFAULT: token('line'),
          strong: token('line-strong'),
        },
        ink: {
          DEFAULT: token('ink'),
          muted: token('ink-muted'),
          subtle: token('ink-subtle'),
        },
        brand: {
          DEFAULT: token('brand'),
          hover: token('brand-hover'),
          soft: token('brand-soft'),
          on: token('brand-on'),
        },
        ok: { DEFAULT: token('ok'), soft: token('ok-soft') },
        warn: { DEFAULT: token('warn'), soft: token('warn-soft') },
        crit: { DEFAULT: token('crit'), soft: token('crit-soft') },
        info: { DEFAULT: token('info'), soft: token('info-soft') },
        sev: {
          normal: { DEFAULT: token('sev-normal'), soft: token('sev-normal-soft') },
          moderate: { DEFAULT: token('sev-moderate'), soft: token('sev-moderate-soft') },
          stressed: { DEFAULT: token('sev-stressed'), soft: token('sev-stressed-soft') },
          warning: { DEFAULT: token('sev-warning'), soft: token('sev-warning-soft') },
          severe: { DEFAULT: token('sev-severe'), soft: token('sev-severe-soft') },
          critical: { DEFAULT: token('sev-critical'), soft: token('sev-critical-soft') },
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        // One scale. Left column is the name used in components.
        micro: ['0.625rem', { lineHeight: '1', letterSpacing: '0.14em' }], // 10px uppercase labels
        caption: ['0.6875rem', { lineHeight: '1.4' }],                      // 11px helper text
        sm: ['0.8125rem', { lineHeight: '1.45' }],                          // 13px body / table
        base: ['0.875rem', { lineHeight: '1.6' }],                          // 14px prose
        lead: ['1rem', { lineHeight: '1.6' }],                              // 16px intro
        h3: ['1.0625rem', { lineHeight: '1.4', letterSpacing: '-0.005em' }],
        h2: ['1.25rem', { lineHeight: '1.35', letterSpacing: '-0.01em' }],
        h1: ['1.5rem', { lineHeight: '1.3', letterSpacing: '-0.015em' }],
        metric: ['1.6875rem', { lineHeight: '1.1', letterSpacing: '-0.02em' }], // KPI value
      },
      borderRadius: {
        DEFAULT: '6px',
        sm: '4px',
        md: '6px',
        lg: '8px',
        xl: '10px',
      },
      boxShadow: {
        // Elevation is carried by borders; shadows stay almost invisible.
        card: '0 1px 2px rgb(20 26 33 / 0.04)',
        pop: '0 8px 24px rgb(20 26 33 / 0.10), 0 2px 6px rgb(20 26 33 / 0.06)',
      },
      transitionDuration: {
        DEFAULT: '150ms',
      },
    },
  },
  plugins: [],
}
