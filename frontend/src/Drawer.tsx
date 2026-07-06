import { band, dimColor, prettyName } from './lib'
import type { ScreeningJob } from './types'

export function Drawer({
  job,
  presetName,
  chip,
  onClose,
}: {
  job: ScreeningJob
  presetName: string
  chip: { bg: string; fg: string }
  onClose: () => void
}) {
  const r = job.result
  const bd = r ? band(r.overall_score) : null
  const score = r ? Math.round(r.overall_score) : 0
  const dash = r ? Math.round((r.overall_score / 100) * 201) : 0

  return (
    <>
      <div className="sb-scrim" onClick={onClose} />
      <aside className="sb-drawer">
        <div className="head">
          <div className="grow">
            <div className="who">{r?.candidate_name || prettyName(job.filename)}</div>
            <div className="meta">
              <span className="file">{job.filename}</span>
              <span className="sb-chip" style={{ background: chip.bg, color: chip.fg }}>
                {presetName}
              </span>
            </div>
          </div>
          <button className="sb-iconbtn" style={{ fontSize: 16, lineHeight: 1 }} onClick={onClose}>
            ×
          </button>
        </div>

        <div className="body">
          {job.status === 'failed' && (
            <div className="sb-failcard">
              <div className="t">Screening failed</div>
              <div className="m">{job.error}</div>
              <div className="n">Other rows in the pile were not affected. The file was not stored.</div>
            </div>
          )}

          {job.status === 'done' && r && (
            <>
              <div className="sb-scorecard">
                <div className="sb-ring">
                  <svg width="76" height="76" viewBox="0 0 76 76">
                    <circle cx="38" cy="38" r="32" fill="none" stroke="var(--line)" strokeWidth="6" />
                    <circle
                      cx="38"
                      cy="38"
                      r="32"
                      fill="none"
                      stroke={bd!.color}
                      strokeWidth="6"
                      strokeLinecap="round"
                      strokeDasharray={`${dash} 201`}
                      transform="rotate(-90 38 38)"
                    />
                  </svg>
                  <div className="num">{score}</div>
                </div>
                <div style={{ minWidth: 0 }}>
                  <div className="sb-band" style={{ color: bd!.color }}>
                    {bd!.label} · {score}/100
                  </div>
                  <div className="sb-verdict">{r.verdict}</div>
                </div>
              </div>
              <p className="sb-triagenote">
                A triage aid, not a ranking of people — small score gaps aren’t meaningful. The
                evidence below is the substance.
              </p>

              <h3 className="sect">Dimension breakdown</h3>
              <div>
                {r.dimensions.map((d) => (
                  <div key={d.key} className="sb-dim">
                    <div className="toprow">
                      <span className="nm">{d.name}</span>
                      <span className="wt">{Math.round(d.weight * 100)}% weight</span>
                      <div className="sb-spacer" />
                      <span className="sc" style={{ color: dimColor(d.score) }}>
                        {d.score}
                        <span className="max">/10</span>
                      </span>
                    </div>
                    <div className="sb-dimbar">
                      <div style={{ width: `${d.score * 10}%`, background: dimColor(d.score) }} />
                    </div>
                    <p className="sb-evidence">{d.evidence}</p>
                  </div>
                ))}
              </div>

              <div className="sb-twocol">
                <div>
                  <h3 style={{ color: 'var(--good)' }}>Key strengths</h3>
                  <div className="list">
                    {r.key_strengths.map((s, i) => (
                      <div key={i} className="sb-pointrow">
                        <span className="pm" style={{ color: 'var(--good)' }}>
                          +
                        </span>
                        <span>{s}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <h3 style={{ color: 'var(--mid)' }}>Concerns</h3>
                  <div className="list">
                    {r.concerns.map((c, i) => (
                      <div key={i} className="sb-pointrow">
                        <span className="pm" style={{ color: 'var(--mid)' }}>
                          !
                        </span>
                        <span>{c}</span>
                      </div>
                    ))}
                    {r.concerns.length === 0 && <div className="sb-nonefound">None flagged.</div>}
                  </div>
                </div>
              </div>

              <div className="sb-rubricnote">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M12 8v5l3 2" />
                  <circle cx="12" cy="12" r="9" />
                </svg>
                The full rubric snapshot is saved with this result — later preset edits won’t change it.
              </div>
            </>
          )}
        </div>
      </aside>
    </>
  )
}
