// packages/dashboard/src/lib/utils.ts
import { clsx, type ClassValue } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

// tailwind-merge only knows Tailwind's stock scale. Our type scale lives in
// tailwind.config.js, so without this it treats `text-micro` as a text-colour
// class and silently drops it when a real colour follows (text-micro
// text-sev-normal -> text-sev-normal).
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [
        { text: ['micro', 'caption', 'lead', 'h1', 'h2', 'h3', 'metric'] },
      ],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
