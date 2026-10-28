import { pinyin } from 'pinyin-pro'

function compact(value: string) {
  return value.replace(/[\s']/g, '')
}

// Build outside keyword-dependent filters so typing reuses the transliterations.
export function buildSearchIndex(values: string[]): string[] {
  return values.flatMap((value) => {
    const text = value.toLowerCase()
    return [
      text,
      compact(pinyin(text, { toneType: 'none', nonZh: 'consecutive', v: true })),
      compact(pinyin(text, { pattern: 'first', toneType: 'none', nonZh: 'consecutive' })),
    ]
  })
}

export function matchesSearch(index: string[], query: string): boolean {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return true
  const joined = compact(normalized)
  return index.some((text) => text.includes(normalized) || (joined !== '' && text.includes(joined)))
}
