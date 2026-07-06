import type { Preset, ScreeningJob } from './types'

async function check(resp: Response): Promise<Response> {
  if (resp.ok) return resp
  let detail = `${resp.status} ${resp.statusText}`
  try {
    const body = await resp.json()
    if (body.detail) {
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    }
  } catch {
    /* non-JSON error body */
  }
  throw new Error(detail)
}

export async function listPresets(): Promise<Preset[]> {
  return (await check(await fetch('/api/presets'))).json()
}

export async function createPreset(preset: Preset): Promise<Preset> {
  return (
    await check(
      await fetch('/api/presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(preset),
      }),
    )
  ).json()
}

export async function updatePreset(preset: Preset): Promise<Preset> {
  return (
    await check(
      await fetch(`/api/presets/${preset.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(preset),
      }),
    )
  ).json()
}

export async function deletePreset(id: string): Promise<void> {
  await check(await fetch(`/api/presets/${id}`, { method: 'DELETE' }))
}

export async function createScreening(file: File, presetId: string): Promise<ScreeningJob> {
  const form = new FormData()
  form.append('file', file)
  form.append('preset_id', presetId)
  return (await check(await fetch('/api/screenings', { method: 'POST', body: form }))).json()
}

export async function listScreenings(): Promise<ScreeningJob[]> {
  return (await check(await fetch('/api/screenings'))).json()
}

export async function getScreening(id: string): Promise<ScreeningJob> {
  return (await check(await fetch(`/api/screenings/${id}`))).json()
}
