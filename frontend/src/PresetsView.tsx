import { useState } from 'react'
import * as api from './api'
import { chipColors, validateDraft, weightPct, type DraftErrors } from './lib'
import type { Preset, RubricDimension } from './types'

interface Draft {
  isNew: boolean
  id: string | null
  name: string
  role_description: string
  enrichments: { github: boolean }
  dimensions: RubricDimension[]
}

const emptyDraft = (): Draft => ({
  isNew: true,
  id: null,
  name: '',
  role_description: '',
  enrichments: { github: false },
  dimensions: [{ key: '', name: '', weight: 25, guidance: '' }],
})

const draftFrom = (p: Preset): Draft => ({
  isNew: false,
  id: p.id,
  name: p.name,
  role_description: p.role_description,
  enrichments: { ...p.enrichments },
  dimensions: p.dimensions.map((d) => ({ ...d })),
})

export function PresetsView({ presets, onChanged }: { presets: Preset[]; onChanged: () => void }) {
  const [draft, setDraft] = useState<Draft | null>(null)
  const [errors, setErrors] = useState<DraftErrors>({ dims: {} })
  const [banner, setBanner] = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const presetIds = presets.map((p) => p.id)

  function openEditor(d: Draft) {
    setDraft(d)
    setErrors({ dims: {} })
    setBanner(null)
    setConfirmDeleteId(null)
  }

  async function save() {
    if (!draft || saving) return
    const v = validateDraft(draft, draft.isNew)
    setErrors(v.errors)
    setBanner(v.banner)
    if (!v.cleaned) return
    setSaving(true)
    try {
      if (draft.isNew) await api.createPreset(v.cleaned)
      else await api.updatePreset(v.cleaned)
      setDraft(null)
      onChanged()
    } catch (e) {
      setBanner((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function confirmDelete(id: string) {
    try {
      await api.deletePreset(id)
      setConfirmDeleteId(null)
      onChanged()
    } catch (e) {
      setConfirmDeleteId(null)
      setBanner((e as Error).message)
    }
  }

  const patchDim = (i: number, patch: Partial<RubricDimension>) =>
    setDraft((d) =>
      d ? { ...d, dimensions: d.dimensions.map((dim, j) => (j === i ? { ...dim, ...patch } : dim)) } : d,
    )

  const moveDim = (i: number, dir: -1 | 1) =>
    setDraft((d) => {
      if (!d) return d
      const j = i + dir
      if (j < 0 || j >= d.dimensions.length) return d
      const dims = [...d.dimensions]
      ;[dims[i], dims[j]] = [dims[j], dims[i]]
      return { ...d, dimensions: dims }
    })

  if (draft) {
    const pct = weightPct(draft.dimensions)
    const weightSum = draft.dimensions.reduce(
      (a, d) => a + (Number(d.weight) > 0 ? Number(d.weight) : 0),
      0,
    )
    return (
      <main className="sb-main sb-main--narrow">
        <div className="sb-editor sb-fadein">
          <button className="sb-back" onClick={() => setDraft(null)}>
            ← All presets
          </button>
          <h2>{draft.isNew ? 'New preset' : `Edit “${draft.name}”`}</h2>
          {draft.isNew ? (
            <p className="note">
              The role description and each dimension’s guidance are read by the AI — write them
              like you’d brief a new screener.
            </p>
          ) : (
            <p className="note">
              Changes apply to future screenings only — past results keep the rubric they were
              scored with.
            </p>
          )}

          {banner && <div className="sb-banner">{banner}</div>}

          <section className="sb-card sb-formcard">
            <label className="sb-field">
              <span className="lbl">Preset name</span>
              <input
                className={errors.name ? 'err' : ''}
                value={draft.name}
                placeholder="e.g. Founding Software Engineer"
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </label>
            <label className="sb-field">
              <span className="lbl">
                Role description <span className="soft">— read by the AI</span>
              </span>
              <textarea
                rows={3}
                value={draft.role_description}
                placeholder="2–4 sentences on what this role does and what you value."
                onChange={(e) => setDraft({ ...draft, role_description: e.target.value })}
              />
            </label>
          </section>

          <div className="sb-dimshead">
            <h3>Dimensions</h3>
            <span className="hint">
              Weights can be any positive numbers — they’re normalized to the live % shown.
            </span>
            <div className="sb-spacer" />
            <span className={`sb-weightsum ${weightSum === 100 ? 'sb-weightsum--ok' : ''}`}>
              weights total {weightSum}
            </span>
          </div>

          <div className="sb-dimlist">
            {draft.dimensions.map((d, i) => {
              const de = errors.dims[i] ?? {}
              return (
                <section key={i} className="sb-card sb-dimcard">
                  <div className="sb-dimgrid">
                    <label className="sb-field">
                      <span className="lbl--sm lbl">DIMENSION {i + 1}</span>
                      <input
                        className={`namein ${de.name ? 'err' : ''}`}
                        value={d.name}
                        placeholder="Display name"
                        onChange={(e) => patchDim(i, { name: e.target.value })}
                      />
                    </label>
                    <label className="sb-field">
                      <span className="lbl--sm lbl">WEIGHT</span>
                      <input
                        type="number"
                        min={0}
                        className={de.weight ? 'err' : ''}
                        value={d.weight}
                        onChange={(e) => patchDim(i, { weight: e.target.value as unknown as number })}
                      />
                    </label>
                    <div className="pctlbl">= {pct(d.weight)}% of score</div>
                    <div className="rowbtns">
                      <button className="sb-sqbtn" title="Move up" onClick={() => moveDim(i, -1)}>
                        ↑
                      </button>
                      <button className="sb-sqbtn" title="Move down" onClick={() => moveDim(i, 1)}>
                        ↓
                      </button>
                      <button
                        className="sb-sqbtn sb-sqbtn--x"
                        title="Remove dimension"
                        onClick={() =>
                          setDraft({ ...draft, dimensions: draft.dimensions.filter((_, j) => j !== i) })
                        }
                      >
                        ×
                      </button>
                    </div>
                  </div>
                  <label className="sb-field guidefield">
                    <span className="lbl--sm lbl">
                      GUIDANCE <span className="soft">— what does good evidence look like? Read by the AI.</span>
                    </span>
                    <textarea
                      rows={2}
                      className={`guidein ${de.guidance ? 'err' : ''}`}
                      value={d.guidance}
                      placeholder="Describe the evidence that should score highly here…"
                      onChange={(e) => patchDim(i, { guidance: e.target.value })}
                    />
                  </label>
                </section>
              )
            })}
          </div>

          <button
            className="sb-adddim"
            onClick={() =>
              setDraft({
                ...draft,
                dimensions: [...draft.dimensions, { key: '', name: '', weight: 10, guidance: '' }],
              })
            }
          >
            + Add dimension
          </button>

          <h3 className="sect">Enrichments</h3>
          <section className="sb-card sb-enrichrow">
            <div className="grow">
              <div className="t">GitHub analysis</div>
              <div className="d">
                Fetches and classifies the candidate’s public repos. Adds ~30s per resume; only
                meaningful for engineering roles.
              </div>
            </div>
            <button
              role="switch"
              aria-checked={draft.enrichments.github}
              className={`sb-switch ${draft.enrichments.github ? 'sb-switch--on' : ''}`}
              onClick={() => setDraft({ ...draft, enrichments: { github: !draft.enrichments.github } })}
            >
              <span />
            </button>
          </section>

          <div className="sb-editactions">
            <button className="sb-btn" onClick={save} disabled={saving}>
              {saving ? 'Saving…' : draft.isNew ? 'Create preset' : 'Save changes'}
            </button>
            <button className="sb-btn sb-btn--ghost" onClick={() => setDraft(null)}>
              Cancel
            </button>
          </div>
        </div>
      </main>
    )
  }

  return (
    <main className="sb-main sb-main--narrow">
      <div className="sb-presetshead">
        <h2>Role presets</h2>
        <span className="sub">
          The rubric each resume is scored against — the role description and guidance are read by
          the AI.
        </span>
        <div className="sb-spacer" />
        <button className="sb-btn sb-btn--sm" onClick={() => openEditor(emptyDraft())}>
          New preset
        </button>
      </div>

      {banner && <div className="sb-banner">{banner}</div>}

      <div className="sb-presetlist">
        {presets.map((p) => {
          const chip = chipColors(p.id, presetIds)
          const pct = weightPct(p.dimensions)
          const confirming = confirmDeleteId === p.id
          return (
            <section key={p.id} className="sb-card sb-presetcard">
              <div className="toprow">
                <span className="nm">{p.name}</span>
                <span className="sb-chip" style={{ background: chip.bg, color: chip.fg }}>
                  {p.dimensions.length} dimensions
                </span>
                {p.enrichments.github && (
                  <span className="sb-chip" style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>
                    GitHub analysis on
                  </span>
                )}
                <div className="sb-spacer" />
                {confirming ? (
                  <>
                    <span className="sb-confirmtext">
                      Delete “{p.name}”? Past scores keep their snapshot.
                    </span>
                    <button className="sb-minibtn sb-minibtn--reddanger" onClick={() => confirmDelete(p.id)}>
                      Delete
                    </button>
                    <button className="sb-minibtn" onClick={() => setConfirmDeleteId(null)}>
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    <button className="sb-minibtn" onClick={() => openEditor(draftFrom(p))}>
                      Edit
                    </button>
                    <button className="sb-minibtn sb-minibtn--danger" onClick={() => setConfirmDeleteId(p.id)}>
                      Delete
                    </button>
                  </>
                )}
              </div>
              <p className="desc">{p.role_description}</p>
              <div className="dims">
                {p.dimensions.map((d) => (
                  <span key={d.key} className="sb-dimtag">
                    {d.name} <span className="pct">{pct(d.weight)}%</span>
                  </span>
                ))}
              </div>
            </section>
          )
        })}
      </div>
    </main>
  )
}
