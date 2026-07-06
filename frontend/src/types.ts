// Mirrors the backend Pydantic models (backend/pipeline/presets.py, screening.py, api/main.py)

export interface RubricDimension {
  key: string
  name: string
  weight: number
  guidance: string
}

export interface Preset {
  id: string
  name: string
  role_description: string
  dimensions: RubricDimension[]
  enrichments: { github: boolean }
}

export interface ScoredDimension {
  key: string
  name: string
  weight: number // normalized fraction, sums to 1
  score: number // 0-10
  evidence: string
}

export interface ScreeningResult {
  candidate_name: string | null
  preset_id: string
  preset_name: string
  rubric_snapshot: Preset
  overall_score: number
  dimensions: ScoredDimension[]
  key_strengths: string[]
  concerns: string[]
  verdict: string
}

export type JobStatus = 'queued' | 'parsing' | 'enriching' | 'scoring' | 'done' | 'failed'

export interface ScreeningJob {
  id: string
  filename: string
  preset_id: string
  status: JobStatus
  error: string | null
  result: ScreeningResult | null
}
