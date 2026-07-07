import { describe, expect, it } from 'vitest'
import {
  band,
  dimColor,
  dimensionKey,
  presetId,
  prettyName,
  stageInfo,
  validateDraft,
  weightPct,
} from './lib'
import type { RubricDimension } from './types'

describe('prettyName', () => {
  it('cleans filename noise into a display name', () => {
    expect(prettyName('jane_doe-resume.pdf')).toBe('Jane Doe')
    expect(prettyName('marcus chen final.pdf')).toBe('Marcus Chen')
    expect(prettyName('Tok Jing Huan.pdf')).toBe('Tok Jing Huan')
    expect(prettyName('resume.pdf')).toBe('resume.pdf') // nothing left after stripping
  })
})

describe('band / dimColor', () => {
  it('maps score bands per design', () => {
    expect(band(84).label).toBe('strong signal')
    expect(band(70).label).toBe('strong signal')
    expect(band(69.9).label).toBe('mixed signal')
    expect(band(50).label).toBe('mixed signal')
    expect(band(49).label).toBe('weak match')
  })
  it('maps dimension colors per design', () => {
    expect(dimColor(7)).toBe('var(--good)')
    expect(dimColor(5)).toBe('var(--mid)')
    expect(dimColor(4)).toBe('var(--low)')
  })
})

describe('stageInfo', () => {
  it('includes enriching stage only for github presets', () => {
    expect(stageInfo('enriching', true).label).toBe('analyzing GitHub…')
    expect(stageInfo('scoring', false).pct).toBeGreaterThan(stageInfo('parsing', false).pct)
    // 3-stage pipeline: scoring = 3/4; 4-stage pipeline: scoring = 4/5
    expect(stageInfo('scoring', false).pct).toBe(75)
    expect(stageInfo('scoring', true).pct).toBe(80)
  })
})

describe('weightPct', () => {
  const dims = (...w: number[]): RubricDimension[] =>
    w.map((weight, i) => ({ key: `k${i}`, name: `D${i}`, weight, guidance: 'g' }))

  it('normalizes to live percentages', () => {
    const pct = weightPct(dims(30, 45, 25))
    expect(pct(30)).toBe(30)
    expect(pct(45)).toBe(45)
  })
  it('handles non-100 totals', () => {
    const pct = weightPct(dims(2, 6))
    expect(pct(2)).toBe(25)
    expect(pct(6)).toBe(75)
  })
  it('returns 0 when total is 0', () => {
    expect(weightPct(dims())(5)).toBe(0)
  })
})

describe('slugs', () => {
  it('makes backend-valid dimension keys', () => {
    expect(dimensionKey('Communication & Persuasion')).toBe('communication_persuasion')
    expect(dimensionKey('0-to-1 Shipping')).toBe('d_0_to_1_shipping') // must start with a letter
    expect(dimensionKey('  ')).toBe('')
  })
  it('makes backend-valid preset ids', () => {
    expect(presetId('Software Engineer')).toBe('founding-software-engineer')
    expect(presetId('3D Artist')).toBe('p-3d-artist')
  })
})

describe('validateDraft', () => {
  const draft = () => ({
    id: null,
    name: 'Designer',
    role_description: 'Designs.',
    enrichments: { github: false },
    dimensions: [
      { key: '', name: 'Portfolio', weight: 60, guidance: 'Linked work.' },
      { key: '', name: 'Craft', weight: 40, guidance: 'Attention to detail.' },
    ],
  })

  it('accepts a valid draft and slugs ids/keys', () => {
    const v = validateDraft(draft(), true)
    expect(v.banner).toBeNull()
    expect(v.cleaned).toMatchObject({
      id: 'designer',
      dimensions: [{ key: 'portfolio' }, { key: 'craft' }],
    })
  })

  it('rejects empty name, empty guidance, zero weights', () => {
    const d = draft()
    d.name = ''
    d.dimensions[0].guidance = ' '
    d.dimensions[1].weight = 0
    const v = validateDraft(d, true)
    expect(v.cleaned).toBeNull()
    expect(v.errors.name).toBe(true)
    expect(v.errors.dims[0].guidance).toBe(true)
    expect(v.errors.dims[1].weight).toBe(true)
  })

  it('rejects duplicate dimension names (same slug)', () => {
    const d = draft()
    d.dimensions[1].name = 'Portfolio!'
    const v = validateDraft(d, true)
    expect(v.cleaned).toBeNull()
    expect(v.banner).toMatch(/same name/)
  })

  it('rejects zero dimensions', () => {
    const d = draft()
    d.dimensions = []
    expect(validateDraft(d, true).banner).toMatch(/at least one dimension/)
  })

  it('keeps the existing id when editing', () => {
    const d = { ...draft(), id: 'bd-intern', name: 'Renamed Role' }
    const v = validateDraft(d, false)
    expect(v.cleaned?.id).toBe('bd-intern')
  })
})
