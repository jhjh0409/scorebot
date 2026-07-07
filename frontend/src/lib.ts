// Pure view logic ported from the design mockup (docs/design/scorebot-A.dc.html)

import type { JobStatus, Preset, RubricDimension } from './types'

/** "jane_doe-resume_final.pdf" -> "Jane Doe" — placeholder name while parsing. */
export function prettyName(filename: string): string {
  return (
    filename
      .replace(/\.pdf$/i, '')
      .replace(/resume|_cv|cv_|\bfinal\b/gi, ' ')
      .replace(/[_\-.]+/g, ' ')
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ') || filename
  )
}

export function band(score: number): { label: string; color: string } {
  if (score >= 70) return { label: 'strong signal', color: 'var(--good)' }
  if (score >= 50) return { label: 'mixed signal', color: 'var(--mid)' }
  return { label: 'weak match', color: 'var(--low)' }
}

export function dimColor(score: number): string {
  if (score >= 7) return 'var(--good)'
  if (score >= 5) return 'var(--mid)'
  return 'var(--low)'
}

const TINTS = [
  { bg: 'var(--tint-a-bg)', fg: 'var(--tint-a-fg)' },
  { bg: 'var(--tint-b-bg)', fg: 'var(--tint-b-fg)' },
  { bg: 'var(--tint-c-bg)', fg: 'var(--tint-c-fg)' },
]

/** Stable chip tint per preset: seed order first, then hash for customs. */
export function chipColors(presetId: string, presetIds: string[]): { bg: string; fg: string } {
  const idx = presetIds.indexOf(presetId)
  if (idx >= 0) return TINTS[idx % TINTS.length]
  let h = 0
  for (const c of presetId) h = (h * 31 + c.charCodeAt(0)) | 0
  return TINTS[Math.abs(h) % TINTS.length]
}

export function shortName(name: string): string {
  return name
    .replace('Software Engineer', 'SWE')
    .replace('Business Development Intern', 'BD Intern')
    .replace('Software Engineer', 'SWE')
}

export function stageInfo(
  status: JobStatus,
  githubEnrichment: boolean,
): { label: string; pct: number } {
  const stages: JobStatus[] = ['queued', 'parsing', ...(githubEnrichment ? (['enriching'] as JobStatus[]) : []), 'scoring']
  const labels: Record<string, string> = {
    queued: 'queued',
    parsing: 'parsing resume…',
    enriching: 'analyzing GitHub…',
    scoring: 'scoring…',
  }
  const idx = stages.indexOf(status)
  return {
    label: labels[status] ?? status,
    pct: Math.round(((idx + 1) / (stages.length + 1)) * 100),
  }
}

export function weightPct(dimensions: RubricDimension[]): (weight: number) => number {
  const total = dimensions.reduce((a, d) => a + (Number(d.weight) > 0 ? Number(d.weight) : 0), 0)
  return (weight: number) => {
    const w = Number(weight)
    return total > 0 && w > 0 ? Math.round((w / total) * 100) : 0
  }
}

/** Backend key pattern: ^[a-z][a-z0-9_]*$ — slug a display name into a valid key. */
export function dimensionKey(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return /^[a-z]/.test(slug) ? slug : slug ? `d_${slug}` : ''
}

/** Backend id pattern: ^[a-z][a-z0-9-]*$ */
export function presetId(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return /^[a-z]/.test(slug) ? slug : slug ? `p-${slug}` : ''
}

export interface DraftErrors {
  name?: boolean
  dims: Record<number, { name?: boolean; guidance?: boolean; weight?: boolean }>
}

export interface DraftValidation {
  errors: DraftErrors
  banner: string | null
  /** Draft normalized into a backend-shaped Preset (only when valid). */
  cleaned: Preset | null
}

/** Client-side mirror of backend preset validation, ported from the mockup. */
export function validateDraft(
  draft: { id: string | null; name: string; role_description: string; enrichments: { github: boolean }; dimensions: RubricDimension[] },
  isNew: boolean,
): DraftValidation {
  const errors: DraftErrors = { dims: {} }
  let banner: string | null = null

  if (!draft.name.trim()) {
    errors.name = true
    banner = 'Fix the highlighted fields.'
  }
  const seen: Record<string, boolean> = {}
  draft.dimensions.forEach((dim, i) => {
    const e: { name?: boolean; guidance?: boolean; weight?: boolean } = {}
    if (!dim.name.trim()) e.name = true
    if (!dim.guidance.trim()) e.guidance = true
    if (!(Number(dim.weight) > 0)) e.weight = true
    const slug = dimensionKey(dim.name)
    if (slug && seen[slug]) {
      e.name = true
      banner = 'Two dimensions have the same name — ids must be unique.'
    }
    seen[slug] = true
    if (Object.keys(e).length) {
      errors.dims[i] = e
      banner = banner || 'Fix the highlighted fields — guidance can’t be empty and weights must be positive.'
    }
  })
  if (draft.dimensions.length === 0) banner = 'A preset needs at least one dimension.'
  if (!banner && errors.name) banner = 'Fix the highlighted fields.'
  if (banner) return { errors, banner, cleaned: null }

  const cleaned: Preset = {
    id: isNew ? presetId(draft.name) : (draft.id as string),
    name: draft.name.trim(),
    role_description: draft.role_description.trim() || draft.name.trim(),
    enrichments: { github: draft.enrichments.github },
    dimensions: draft.dimensions.map((d) => ({
      key: dimensionKey(d.name),
      name: d.name.trim(),
      weight: Number(d.weight),
      guidance: d.guidance.trim(),
    })),
  }
  return { errors: { dims: {} }, banner: null, cleaned }
}
