export type TutorialLink = {
  id: string
  source: 'youtube' | 'article' | 'web'
  title: string
  url: string
  reason: string
}

export type TutorialLinksResponse = {
  idea_id: string
  tutorial_links: TutorialLink[]
  links_mode: 'grounded' | 'fallback'
  timings_ms: Record<string, number>
}

export type Idea = {
  id: string
  title: string
  description: string
  difficulty: 'easy' | 'medium' | 'hard'
  why_this_works: string
  materials: string[]
  steps: string[]
  search_query: string
  visualization_prompt: string
  tutorial_links: TutorialLink[]
}

export type ScanResponse = {
  scan_id: string
  detected_label: string
  confidence: number
  summary: string
  safety_note: string
  source_mode: 'gemini' | 'mock'
  provider_state: 'ok' | 'not_configured' | 'fallback_invalid_key' | 'fallback_error'
  provider_notice: string | null
  image_asset_key: string | null
  created_at: string
  ideas: Idea[]
  timings_ms: Record<string, number>
}

export type VisualizationResponse = {
  idea_id: string
  model: string
  mime_type: string
  image_base64: string
  caption: string
  timings_ms: Record<string, number>
}

export type HealthResponse = {
  status: string
  gemini_configured: 'yes' | 'no'
  mock_fallback_enabled: 'yes' | 'no'
  max_upload_megabytes: number
  analysis_model: string
  search_model: string
  image_model: string
  visualization_mode: 'async' | 'inline'
  visualization_jobs_enabled: 'yes' | 'no'
  visualization_jobs_configured: 'yes' | 'no'
}

export type VisualizationJobStatus = 'queued' | 'processing' | 'completed' | 'failed'

export type VisualizationJobResponse = {
  job_id: string
  idea_id: string
  status: VisualizationJobStatus
  source_mode: 'async' | 'inline'
  created_at: string
  updated_at: string
  result: VisualizationResponse | null
  error: string | null
  timings_ms: Record<string, number>
  poll_after_ms: number | null
}

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim()
const API_BASE_URL = configuredBaseUrl ? configuredBaseUrl.replace(/\/$/, '') : '/api'

async function readErrorMessage(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: string }
    return payload.detail ?? 'Request failed.'
  } catch {
    return 'Request failed.'
  }
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`)

  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }

  return response.json() as Promise<HealthResponse>
}

export async function submitScan(imageFile: File): Promise<ScanResponse> {
  const formData = new FormData()
  formData.append('image', imageFile)

  const response = await fetch(`${API_BASE_URL}/scan`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }

  return response.json() as Promise<ScanResponse>
}

export async function generateVisualization(args: {
  imageFile: File
  detectedLabel: string
  idea: Idea
}): Promise<VisualizationResponse> {
  const formData = new FormData()
  formData.append('image', args.imageFile)
  formData.append('idea_id', args.idea.id)
  formData.append('detected_label', args.detectedLabel)
  formData.append('idea_title', args.idea.title)
  formData.append('idea_description', args.idea.description)
  formData.append('visualization_prompt', args.idea.visualization_prompt)

  const response = await fetch(`${API_BASE_URL}/visualize`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }

  return response.json() as Promise<VisualizationResponse>
}

export async function createVisualizationJob(args: {
  imageFile?: File
  imageAssetKey?: string
  detectedLabel: string
  idea: Idea
}): Promise<VisualizationJobResponse> {
  const formData = new FormData()
  if (args.imageFile) {
    formData.append('image', args.imageFile)
  }
  if (args.imageAssetKey) {
    formData.append('image_asset_key', args.imageAssetKey)
  }
  formData.append('idea_id', args.idea.id)
  formData.append('detected_label', args.detectedLabel)
  formData.append('idea_title', args.idea.title)
  formData.append('idea_description', args.idea.description)
  formData.append('visualization_prompt', args.idea.visualization_prompt)

  const response = await fetch(`${API_BASE_URL}/visualize/jobs`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }

  return response.json() as Promise<VisualizationJobResponse>
}

export async function getVisualizationJob(jobId: string): Promise<VisualizationJobResponse> {
  const response = await fetch(`${API_BASE_URL}/visualize/jobs/${jobId}`)

  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }

  return response.json() as Promise<VisualizationJobResponse>
}

export async function fetchTutorialLinks(args: {
  detectedLabel: string
  idea: Idea
}): Promise<TutorialLinksResponse> {
  const response = await fetch(`${API_BASE_URL}/links`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      detected_label: args.detectedLabel,
      idea_id: args.idea.id,
      idea_title: args.idea.title,
      idea_description: args.idea.description,
      search_query: args.idea.search_query,
    }),
  })

  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }

  return response.json() as Promise<TutorialLinksResponse>
}
