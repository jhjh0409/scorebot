import { useMemo, useRef, useState } from 'react'
import * as api from './api'
import { band, chipColors, prettyName, shortName, stageInfo, weightPct } from './lib'
import type { Preset, ScreeningJob } from './types'
import { Drawer } from './Drawer'
import { BotLogo } from './App'

const MAX_BYTES = 10 * 1024 * 1024

interface Rejection {
  filename: string
  reason: string
}

export function ScreenView({
  presets,
  jobs,
  onJobsAdded,
}: {
  presets: Preset[]
  jobs: ScreeningJob[]
  onJobsAdded: (jobs: ScreeningJob[]) => void
}) {
  const [activePresetId, setActivePresetId] = useState<string | null>(null)
  const [sortByScore, setSortByScore] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [rejections, setRejections] = useState<Rejection[]>([])
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const presetIds = useMemo(() => presets.map((p) => p.id), [presets])
  const presetById = useMemo(() => new Map(presets.map((p) => [p.id, p])), [presets])
  const active = (activePresetId && presetById.get(activePresetId)) || presets[0]
  const activePct = active ? weightPct(active.dimensions) : () => 0

  async function addFiles(files: File[]) {
    if (!active) return
    const rejected: Rejection[] = []
    const accepted: File[] = []
    for (const f of files) {
      if (!/\.pdf$/i.test(f.name)) {
        rejected.push({ filename: f.name, reason: 'only PDF files are accepted.' })
      } else if (f.size > MAX_BYTES) {
        rejected.push({ filename: f.name, reason: 'it’s larger than the 10 MB limit.' })
      } else {
        accepted.push(f)
      }
    }
    const created: ScreeningJob[] = []
    for (const f of accepted) {
      try {
        created.push(await api.createScreening(f, active.id))
      } catch (e) {
        rejected.push({ filename: f.name, reason: (e as Error).message })
      }
    }
    setRejections(rejected)
    setDragOver(false)
    if (created.length) onJobsAdded(created)
  }

  const rows = useMemo(() => {
    const list = [...jobs]
    if (sortByScore) {
      const rank = (j: ScreeningJob) => (j.status === 'done' ? 0 : j.status === 'failed' ? 2 : 1)
      list.sort(
        (a, b) =>
          rank(a) - rank(b) ||
          (b.result?.overall_score ?? 0) - (a.result?.overall_score ?? 0),
      )
    }
    return list
  }, [jobs, sortByScore])

  const doneCount = jobs.filter((j) => j.status === 'done').length
  const activeCount = jobs.filter((j) => j.status !== 'done' && j.status !== 'failed').length
  let countLabel = `${jobs.length} screening${jobs.length === 1 ? '' : 's'}`
  if (activeCount) countLabel += ` · ${activeCount} running`
  else if (doneCount) countLabel += ` · ${doneCount} done`

  const mixedPresets = new Set(jobs.map((j) => j.preset_id)).size > 1
  const selected = jobs.find((j) => j.id === selectedId) ?? null

  return (
    <main className="sb-main">
      <div className="sb-controls">
        <section className="sb-card sb-picker">
          <div className="sb-kicker">1 · Pick a role</div>
          <div className="sb-chiprow">
            {presets.map((p) => (
              <button
                key={p.id}
                className={`sb-presetchip ${active?.id === p.id ? 'sb-presetchip--on' : ''}`}
                onClick={() => setActivePresetId(p.id)}
              >
                {p.name}
              </button>
            ))}
          </div>
          {active && (
            <div className="sb-peek">
              {active.dimensions.map((d) => (
                <span key={d.key} className="sb-dimtag">
                  {d.name} <span className="pct">{activePct(d.weight)}%</span>
                </span>
              ))}
              {active.enrichments.github && <span className="sb-ghbadge">+ GitHub analysis</span>}
            </div>
          )}
        </section>

        <section
          className={`sb-dropzone ${dragOver ? 'sb-dropzone--over' : ''}`}
          onClick={() => fileRef.current?.click()}
          onDrop={(e) => {
            e.preventDefault()
            addFiles([...e.dataTransfer.files])
          }}
          onDragOver={(e) => {
            e.preventDefault()
            if (!dragOver) setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
        >
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
            <path d="M12 15V4M12 4l-3.5 3.5M12 4l3.5 3.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          <div className="title">
            2 · Drop resume PDFs <span>or click to browse</span>
          </div>
          <div className="sub">
            PDF only · 10&thinsp;MB max · scored against <strong>{active?.name ?? '…'}</strong>
          </div>
          <input
            ref={fileRef}
            type="file"
            multiple
            accept="application/pdf"
            style={{ display: 'none' }}
            onChange={(e) => {
              addFiles([...(e.target.files ?? [])])
              e.target.value = ''
            }}
          />
        </section>
      </div>

      {rejections.length > 0 && (
        <div className="sb-rejections">
          <div className="msgs">
            {rejections.map((r, i) => (
              <div key={i} className="msg">
                <strong style={{ fontWeight: 600 }}>{r.filename}</strong> was not added — {r.reason}
              </div>
            ))}
          </div>
          <button className="close" onClick={() => setRejections([])}>
            ×
          </button>
        </div>
      )}

      <div className="sb-resultshead">
        <h2>Screenings</h2>
        <span className="sb-count">{countLabel}</span>
        {jobs.length > 0 && (
          <button
            className={`sb-sortbtn ${sortByScore ? 'sb-sortbtn--on' : ''}`}
            onClick={() => setSortByScore(!sortByScore)}
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
              <path d="M6 4v16M6 20l-3-3M6 20l3-3M13 6h8M13 12h6M13 18h4" />
            </svg>
            Sort by score
          </button>
        )}
        <div className="sb-spacer" />
        <span className="sb-ephemeral">Results last until the server restarts — copy what you need.</span>
      </div>

      <section className="sb-card sb-table">
        {jobs.length === 0 ? (
          <div className="sb-empty">
            <BotLogo size={64} stroke={1.4} />
            <div className="head">Drop resumes, pick a role, get a ranked pile.</div>
            <div className="sub">
              Each resume is scored 0–100 against the role’s rubric, with cited evidence per
              dimension. It’s a first pass — a human still reads every resume.
            </div>
          </div>
        ) : (
          <>
            <div className="sb-tablegrid sb-thead">
              <div>Candidate</div>
              <div>Preset</div>
              <div>Status</div>
              <div className="right">Score</div>
              <div>Verdict</div>
            </div>
            <div>
              {rows.map((j) => {
                const preset = presetById.get(j.preset_id)
                const chip = chipColors(j.preset_id, presetIds)
                const done = j.status === 'done'
                const failed = j.status === 'failed'
                const isActive = !done && !failed
                const st = stageInfo(j.status, preset?.enrichments.github ?? false)
                const bd = done ? band(j.result!.overall_score) : null
                return (
                  <div
                    key={j.id}
                    className={`sb-tablegrid sb-row ${!isActive ? 'sb-row--clickable' : ''} ${selectedId === j.id ? 'sb-row--selected' : ''}`}
                    onClick={() => {
                      if (!isActive) setSelectedId(j.id)
                    }}
                  >
                    <div className="sb-cell">
                      <div className="name">{done ? j.result!.candidate_name || prettyName(j.filename) : prettyName(j.filename)}</div>
                      <div className="file">{j.filename}</div>
                    </div>
                    <div>
                      <span className="sb-chip" style={{ background: chip.bg, color: chip.fg }}>
                        {shortName(preset?.name ?? j.preset_id)}
                      </span>
                    </div>
                    <div>
                      {isActive && (
                        <div className="sb-stage">
                          <span className="sb-spinner" />
                          <span className="col">
                            <span className="lbl">{st.label}</span>
                            <span className="sb-stagebar">
                              <span style={{ width: `${st.pct}%` }} />
                            </span>
                          </span>
                        </div>
                      )}
                      {done && (
                        <span className="sb-status--done">
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M4 13l5 5L20 7" />
                          </svg>
                          done
                        </span>
                      )}
                      {failed && (
                        <span className="sb-status--failed">
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round">
                            <path d="M6 6l12 12M18 6L6 18" />
                          </svg>
                          failed
                        </span>
                      )}
                    </div>
                    <div className="right">
                      {done && (
                        <span className="sb-score">
                          <span className="dot" style={{ background: bd!.color }} />
                          <span className="num">{Math.round(j.result!.overall_score)}</span>
                        </span>
                      )}
                      {isActive && <span className="sb-score-pending">···</span>}
                      {failed && <span className="sb-score-none">—</span>}
                    </div>
                    <div className="sb-cell">
                      {done && <span className="sb-verdictcell">{j.result!.verdict}</span>}
                      {failed && <span className="sb-errorcell">{j.error}</span>}
                      {isActive && <span style={{ fontSize: 12.5, color: 'var(--faint)' }}>&nbsp;</span>}
                    </div>
                  </div>
                )
              })}
            </div>
            {mixedPresets && (
              <div className="sb-mixednote">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 8v5M12 16.5v0.5" />
                </svg>
                This session mixes presets — scores are only comparable within the same preset.
              </div>
            )}
          </>
        )}
      </section>

      {selected && (
        <Drawer
          job={selected}
          presetName={presetById.get(selected.preset_id)?.name ?? selected.preset_id}
          chip={chipColors(selected.preset_id, presetIds)}
          onClose={() => setSelectedId(null)}
        />
      )}
    </main>
  )
}
