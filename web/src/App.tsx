import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import {
  fetchTutorialLinks,
  generateVisualization,
  getHealth,
  submitScan,
  type Idea,
  type ScanResponse,
  type TutorialLink,
  type TutorialLinksResponse,
  type VisualizationResponse,
} from './api'
import './App.css'

const HISTORY_KEY = 'recraft-scan-history-v2'

type VisualizationState = {
  status: 'idle' | 'loading' | 'ready' | 'error'
  response?: VisualizationResponse
  error?: string
}

type DebugEvent = {
  id: string
  message: string
  timestamp: string
}

type TutorialLinksState = {
  status: 'idle' | 'loading' | 'ready' | 'error'
  response?: TutorialLinksResponse
  error?: string
}

type StepStatus = 'pending' | 'active' | 'done' | 'error'

type ProcessingStep = {
  id: string
  label: string
  detail: string
  status: StepStatus
}

function makeInitialSteps(): ProcessingStep[] {
  return [
    { id: 'scan', label: 'Scanning object', detail: 'Identifying item & generating reuse ideas', status: 'pending' },
    { id: 'preview', label: 'Generating preview', detail: 'Rendering a realistic transformation image', status: 'pending' },
    { id: 'tutorials', label: 'Fetching tutorials', detail: 'Finding grounded learning resources', status: 'pending' },
  ]
}

function StepIcon({ status }: { status: StepStatus }) {
  if (status === 'done') {
    return (
      <div className="tracker-step-left icon--done" aria-label="Done">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      </div>
    )
  }
  if (status === 'error') {
    return (
      <div className="tracker-step-left icon--error" aria-label="Error">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </div>
    )
  }
  if (status === 'active') {
    return (
      <div className="tracker-step-left icon--active" aria-label="In progress">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <path d="M12 2a10 10 0 0 1 10 10"></path>
        </svg>
      </div>
    )
  }
  return (
    <div className="tracker-step-left icon--pending" aria-label="Pending">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
      </svg>
    </div>
  )
}

function ProcessingTracker({ steps }: { steps: ProcessingStep[] }) {
  const activeCount = steps.filter((s) => s.status === 'done').length
  const pct = Math.round((activeCount / steps.length) * 100)
  const allDone = steps.every((s) => s.status === 'done' || s.status === 'error')

  return (
    <div className="processing-tracker">
      {/* thin progress bar across top */}
      <div className="pbar-track">
        <div
          className={`pbar-fill ${allDone ? 'pbar-fill--complete' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="tracker-steps">
        {steps.map((step, i) => (
          <div
            key={step.id}
            className={`tracker-step tracker-step--${step.status}`}
            style={{ animationDelay: `${i * 80}ms` }}
          >
            <StepIcon status={step.status} />
            <div className="tracker-step-body">
              <p className="tracker-step-label">{step.label}</p>
              <p className="tracker-step-detail">{step.detail}</p>
            </div>
            <div className="tracker-step-badge">
              {step.status === 'active' && <span className="badge badge--active">Running</span>}
              {step.status === 'done' && <span className="badge badge--done">Done</span>}
              {step.status === 'error' && <span className="badge badge--error">Failed</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function loadHistory() {
  const rawHistory = localStorage.getItem(HISTORY_KEY)
  if (!rawHistory) {
    return []
  }

  try {
    return JSON.parse(rawHistory) as ScanResponse[]
  } catch {
    return []
  }
}

function saveHistory(nextHistory: ScanResponse[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(nextHistory))
}

function formatTimings(timings?: Record<string, number>) {
  if (!timings) {
    return 'n/a'
  }

  const entries = Object.entries(timings).sort(([left], [right]) => left.localeCompare(right))
  if (!entries.length) {
    return 'n/a'
  }

  return entries.map(([key, value]) => `${key}=${value}ms`).join(', ')
}

function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [result, setResult] = useState<ScanResponse | null>(null)
  const [history, setHistory] = useState<ScanResponse[]>(() => loadHistory())
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [activeIdeaId, setActiveIdeaId] = useState<string | null>(null)
  const [visualizations, setVisualizations] = useState<Record<string, VisualizationState>>({})
  const [tutorialLinks, setTutorialLinks] = useState<Record<string, TutorialLinksState>>({})
  const [debugEvents, setDebugEvents] = useState<DebugEvent[]>([])
  const [processingSteps, setProcessingSteps] = useState<ProcessingStep[] | null>(null)
  const cameraInputRef = useRef<HTMLInputElement | null>(null)
  const galleryInputRef = useRef<HTMLInputElement | null>(null)

  /** Helper to update a single step's status. */
  const updateStep = useCallback((id: string, status: StepStatus) => {
    setProcessingSteps((prev) =>
      prev
        ? prev.map((s) => (s.id === id ? { ...s, status } : s))
        : prev,
    )
  }, [])

  const appendDebug = useCallback((message: string) => {
    const timestamp = new Date().toLocaleTimeString()
    const entry = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      message,
      timestamp,
    }
    console.log(`[ReCraft ${timestamp}] ${message}`)
    setDebugEvents((previous) => [entry, ...previous].slice(0, 16))
  }, [])

  const previewUrl = useMemo(() => {
    if (!selectedFile) {
      return null
    }
    return URL.createObjectURL(selectedFile)
  }, [selectedFile])

  const selectedFileSize = useMemo(() => {
    if (!selectedFile) {
      return null
    }

    return `${Math.max(selectedFile.size / (1024 * 1024), 0.01).toFixed(2)} MB`
  }, [selectedFile])

  const activeIdea = useMemo(() => {
    if (!result?.ideas.length) {
      return null
    }

    return result.ideas.find((idea) => idea.id === activeIdeaId) ?? result.ideas[0]
  }, [activeIdeaId, result])

  const activeVisualization = activeIdea ? visualizations[activeIdea.id] : undefined
  const activeTutorialLinksState = activeIdea ? tutorialLinks[activeIdea.id] : undefined
  const activeTutorialLinks: TutorialLink[] = activeIdea
    ? activeTutorialLinksState?.response?.tutorial_links ?? activeIdea.tutorial_links
    : []
  const activeVisualizationUrl =
    activeVisualization?.response
      ? `data:${activeVisualization.response.mime_type};base64,${activeVisualization.response.image_base64}`
      : null

  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl)
      }
    }
  }, [previewUrl])

  useEffect(() => {
    async function checkHealth() {
      try {
        appendDebug('Health check started')
        const nextHealth = await getHealth()
        appendDebug(
          `Health check passed: gemini=${nextHealth.gemini_configured}, analysis=${nextHealth.analysis_model}, image=${nextHealth.image_model}`,
        )
      } catch (healthCheckError) {
        appendDebug(
          `Health check failed: ${healthCheckError instanceof Error ? healthCheckError.message : 'unknown error'
          }`,
        )
      }
    }

    void checkHealth()
  }, [appendDebug])

  useEffect(() => {
    if (!result?.ideas.length) {
      setActiveIdeaId(null)
      return
    }

    setActiveIdeaId((currentId) => currentId ?? result.ideas[0].id)
  }, [result])

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] ?? null
    setSelectedFile(nextFile)
    setResult(null)
    setError(null)
    setVisualizations({})
    setTutorialLinks({})
    setActiveIdeaId(null)
    setProcessingSteps(null)
    appendDebug(
      nextFile
        ? `File selected: ${nextFile.name} (${Math.round(nextFile.size / 1024)} KB, ${nextFile.type || 'unknown type'})`
        : 'File selection cleared',
    )
  }

  const requestVisualization = useCallback(async (idea: Idea, scanResult: ScanResponse, imageFile: File) => {
    appendDebug(
      `Visualization request started for ${idea.id} (${idea.title}) using ${scanResult.detected_label}`,
    )

    // Mark 'preview' step active
    updateStep('preview', 'active')

    setVisualizations((previous) => ({
      ...previous,
      [idea.id]: { status: 'loading' },
    }))

    try {
      const startedAt = performance.now()
      const response = await generateVisualization({
        imageFile,
        detectedLabel: scanResult.detected_label,
        idea,
      })
      const elapsedMs = Math.round(performance.now() - startedAt)
      appendDebug(
        `Visualization request succeeded for ${idea.id} in ${elapsedMs} ms with model ${response.model}`,
      )
      appendDebug(`Visualization timings: ${formatTimings(response.timings_ms)}`)

      setVisualizations((previous) => ({
        ...previous,
        [idea.id]: { status: 'ready', response },
      }))

      // Preview done
      updateStep('preview', 'done')
    } catch (visualizationError) {
      const errorMessage =
        visualizationError instanceof Error
          ? visualizationError.message
          : 'Concept preview could not be generated.'
      appendDebug(`Visualization request failed for ${idea.id}: ${errorMessage}`)
      setVisualizations((previous) => ({
        ...previous,
        [idea.id]: {
          status: 'error',
          error: errorMessage,
        },
      }))

      // Preview errored (don't block rest of flow)
      updateStep('preview', 'error')
    }
  }, [appendDebug, updateStep])

  const requestTutorialLinks = useCallback(async (idea: Idea, scanResult: ScanResponse) => {
    appendDebug(`Tutorial links request started for ${idea.id} (${idea.title})`)

    // Mark tutorials step active
    updateStep('tutorials', 'active')

    setTutorialLinks((previous) => ({
      ...previous,
      [idea.id]: { status: 'loading' },
    }))

    try {
      const startedAt = performance.now()
      const response = await fetchTutorialLinks({
        detectedLabel: scanResult.detected_label,
        idea,
      })
      const elapsedMs = Math.round(performance.now() - startedAt)
      appendDebug(
        `Tutorial links request succeeded for ${idea.id} in ${elapsedMs} ms with mode ${response.links_mode}`,
      )
      appendDebug(`Tutorial links timings: ${formatTimings(response.timings_ms)}`)

      setTutorialLinks((previous) => ({
        ...previous,
        [idea.id]: { status: 'ready', response },
      }))
      setResult((previous) => {
        if (!previous) {
          return previous
        }

        return {
          ...previous,
          ideas: previous.ideas.map((candidate) =>
            candidate.id === idea.id
              ? {
                ...candidate,
                tutorial_links: response.tutorial_links,
              }
              : candidate,
          ),
        }
      })

      // Tutorials done
      updateStep('tutorials', 'done')
    } catch (tutorialLinksError) {
      const errorMessage =
        tutorialLinksError instanceof Error
          ? tutorialLinksError.message
          : 'Related tutorial links could not be refreshed.'
      appendDebug(`Tutorial links request failed for ${idea.id}: ${errorMessage}`)
      setTutorialLinks((previous) => ({
        ...previous,
        [idea.id]: {
          status: 'error',
          error: errorMessage,
        },
      }))

      // Tutorials errored
      updateStep('tutorials', 'error')
    }
  }, [appendDebug, updateStep])

  useEffect(() => {
    if (!result || !activeIdea || !selectedFile) {
      return
    }

    if (result.source_mode !== 'gemini') {
      appendDebug(`Auto visualization skipped because source mode is ${result.source_mode}`)
      return
    }

    const existing = visualizations[activeIdea.id]
    if (existing) {
      appendDebug(
        `Auto visualization not re-triggered for ${activeIdea.id}; existing status=${existing.status}`,
      )
      return
    }

    appendDebug(`Auto visualization triggered for ${activeIdea.id} (${activeIdea.title})`)
    void requestVisualization(activeIdea, result, selectedFile)
  }, [activeIdea, appendDebug, requestVisualization, result, selectedFile, visualizations])

  useEffect(() => {
    if (!result || !activeIdea) {
      return
    }

    if (result.source_mode !== 'gemini') {
      appendDebug(`Tutorial links auto-refresh skipped because source mode is ${result.source_mode}`)
      return
    }

    const existing = tutorialLinks[activeIdea.id]
    if (existing?.status === 'loading' || existing?.status === 'ready') {
      appendDebug(
        `Tutorial links auto-refresh not re-triggered for ${activeIdea.id}; existing status=${existing.status}`,
      )
      return
    }

    appendDebug(`Tutorial links auto-refresh triggered for ${activeIdea.id} (${activeIdea.title})`)
    void requestTutorialLinks(activeIdea, result)
  }, [activeIdea, appendDebug, requestTutorialLinks, result, tutorialLinks])

  async function handleSubmit() {
    if (!selectedFile) {
      setError('Choose a photo before scanning.')
      appendDebug('Scan blocked because no file is selected')
      return
    }

    // Initialize processing steps
    const freshSteps = makeInitialSteps()
    freshSteps[0] = { ...freshSteps[0], status: 'active' }
    setProcessingSteps(freshSteps)

    try {
      setIsSubmitting(true)
      setError(null)
      setVisualizations({})
      setTutorialLinks({})
      appendDebug(`Scan request started for ${selectedFile.name}`)

      const startedAt = performance.now()
      const nextResult = await submitScan(selectedFile)
      const elapsedMs = Math.round(performance.now() - startedAt)

      // Scan done
      updateStep('scan', 'done')

      setResult(nextResult)
      setActiveIdeaId(nextResult.ideas[0]?.id ?? null)
      appendDebug(
        `Scan request succeeded in ${elapsedMs} ms: object=${nextResult.detected_label}, source=${nextResult.source_mode}, provider=${nextResult.provider_state}, ideas=${nextResult.ideas.length}`,
      )
      appendDebug(`Scan timings: ${formatTimings(nextResult.timings_ms)}`)
      if (nextResult.provider_notice) {
        appendDebug(`Provider notice: ${nextResult.provider_notice}`)
      }
      setHistory((previousHistory) => {
        const dedupedHistory = previousHistory.filter((entry) => entry.scan_id !== nextResult.scan_id)
        const nextHistory = [nextResult, ...dedupedHistory].slice(0, 6)
        saveHistory(nextHistory)
        return nextHistory
      })
    } catch (scanError) {
      const errorMessage = scanError instanceof Error ? scanError.message : 'Scan failed.'
      setError(errorMessage)
      appendDebug(`Scan request failed: ${errorMessage}`)
      updateStep('scan', 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  function resetFlow() {
    setSelectedFile(null)
    setResult(null)
    setError(null)
    setVisualizations({})
    setTutorialLinks({})
    setActiveIdeaId(null)
    setProcessingSteps(null)
    appendDebug('Flow reset')
  }

  function loadHistoryEntry(entry: ScanResponse) {
    setSelectedFile(null)
    setResult(entry)
    setError(null)
    setVisualizations({})
    setTutorialLinks({})
    setActiveIdeaId(entry.ideas[0]?.id ?? null)
    setProcessingSteps(null)
    appendDebug(`Loaded history entry ${entry.scan_id} (${entry.detected_label})`)
  }

  function selectIdea(idea: Idea) {
    setActiveIdeaId(idea.id)
    appendDebug(`Idea selected: ${idea.id} (${idea.title})`)
  }

  // Determine if we should show the tracker
  const showTracker = !!processingSteps

  return (
    <main className="app-shell">
      <section className="hero-panel">
        <div className="hero-copy-block">
          <h1>Scan waste. Preview a second life.</h1>
          <p className="hero-copy">
            Upload one object, get grounded reuse ideas, step-by-step guidance, and a realistic
            mockup of how the best transformation could look.
          </p>
        </div>

        <div className="capture-grid">
          <button type="button" className="capture-card" onClick={() => cameraInputRef.current?.click()}>
            <span className="capture-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" /><circle cx="12" cy="13" r="4" /></svg></span>
            <span className="capture-kicker">Camera</span>
            <span className="capture-title">Take a photo</span>
            <span className="capture-copy">Open the mobile camera or capture picker.</span>
            <span className="capture-cta">Open camera</span>
          </button>

          <button
            type="button"
            className="capture-card secondary"
            onClick={() => galleryInputRef.current?.click()}
          >
            <span className="capture-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" /></svg></span>
            <span className="capture-kicker">Library</span>
            <span className="capture-title">Upload from gallery</span>
            <span className="capture-copy">Use an existing photo from your device.</span>
            <span className="capture-cta">Choose photo</span>
          </button>
        </div>

        <input
          ref={cameraInputRef}
          className="visually-hidden-input"
          type="file"
          accept="image/*"
          capture="environment"
          onChange={handleFileChange}
        />
        <input
          ref={galleryInputRef}
          className="visually-hidden-input"
          type="file"
          accept="image/*"
          onChange={handleFileChange}
        />

        {selectedFile ? (
          <div className="selected-file-card">
            <div>
              <p className="selected-file-label">Selected photo</p>
              <p className="selected-file-name">{selectedFile.name}</p>
            </div>
            <span className="selected-file-meta">{selectedFileSize}</span>
          </div>
        ) : null}

        <div className="scan-actions">
          <button
            className={`primary-button primary-button--wide ${isSubmitting ? 'primary-button--loading' : ''}`}
            onClick={handleSubmit}
            disabled={!selectedFile || isSubmitting}
          >
            <span className="btn-text">{isSubmitting ? 'Analyzing object…' : 'Generate reuse plan'}</span>
          </button>
          <button className="ghost-button" onClick={resetFlow} disabled={!selectedFile && !result && !error}>
            Reset
          </button>
        </div>

        {error ? <p className="status-message error-message">{error}</p> : null}

        {/* ── Progress tracker ─────────────────────────────── */}
        {showTracker ? (
          <ProcessingTracker steps={processingSteps!} />
        ) : null}
      </section>

      <section className="workbench-grid">

        <article className="surface-card featured-card">
          <div className="section-heading">
            <p className="section-kicker">Featured reuse</p>
            <h2>{activeIdea ? activeIdea.title : 'Pick a photo to generate ideas'}</h2>
          </div>

          {isSubmitting ? (
            <div className="skeleton-layout">
              <div className="skeleton-item-row">
                <div className="skeleton-text short skeleton-shimmer" style={{ flex: 1 }} />
                <div className="skeleton-text short skeleton-shimmer" style={{ flex: 1 }} />
              </div>
              <div>
                <div className="skeleton-text skeleton-shimmer" />
                <div className="skeleton-text medium skeleton-shimmer" />
              </div>

              <div className="concept-grid">
                <div className="skeleton-concept-panel skeleton-shimmer" />
                <div className="skeleton-concept-panel skeleton-shimmer" />
              </div>

              <div className="skeleton-item-row">
                <div className="skeleton-box skeleton-shimmer" style={{ flex: 1 }} />
                <div className="skeleton-box skeleton-shimmer" style={{ flex: 1 }} />
              </div>
            </div>
          ) : result && activeIdea ? (
            <>
              <div className="result-summary">
                <div>
                  <p className="metric-label">Detected item</p>
                  <p className="metric-value">{result.detected_label}</p>
                </div>
                <div>
                  <p className="metric-label">Confidence</p>
                  <p className="metric-value">{Math.round(result.confidence * 100)}%</p>
                </div>
              </div>

              <div className="result-meta">
                <span className={`mode-pill mode-pill--${result.source_mode}`}>
                  {result.source_mode === 'gemini' ? 'Gemini analysis' : 'Mock fallback'}
                </span>
                <span className="result-time">{new Date(result.created_at).toLocaleString()}</span>
              </div>

              {result.provider_notice ? (
                <p
                  className={`status-message ${result.provider_state === 'fallback_invalid_key' ? 'warning-message' : 'muted-message'
                    }`}
                >
                  {result.provider_notice}
                </p>
              ) : null}

              <p className="result-summary-copy">{result.summary}</p>
              <p className="idea-rationale">{activeIdea.why_this_works}</p>

              <div className="concept-grid">
                <div className="concept-panel">
                  <p className="concept-kicker">Before</p>
                  {previewUrl ? (
                    <img className="concept-image" src={previewUrl} alt="Original object" />
                  ) : (
                    <div className="concept-empty">
                      <p>Original image unavailable.</p>
                      <span>History entries keep the scan details, not the uploaded photo bytes.</span>
                    </div>
                  )}
                </div>

                <div className="concept-panel">
                  <div className="concept-header">
                    <p className="concept-kicker">Reimagined</p>
                    {selectedFile ? (
                      <button
                        type="button"
                        className="inline-action"
                        onClick={() => {
                          if (result && activeIdea) {
                            appendDebug(`Manual visualization requested for ${activeIdea.id}`)
                            void requestVisualization(activeIdea, result, selectedFile)
                          }
                        }}
                      >
                        Regenerate
                      </button>
                    ) : null}
                  </div>

                  {activeVisualization?.status === 'ready' && activeVisualizationUrl ? (
                    <img className="concept-image" src={activeVisualizationUrl} alt={activeVisualization.response?.caption} />
                  ) : null}

                  {activeVisualization?.status === 'loading' ? (
                    <div className="concept-loading">
                      <div className="concept-shimmer" />
                      <p>Rendering a realistic concept preview…</p>
                    </div>
                  ) : null}

                  {activeVisualization?.status === 'error' ? (
                    <div className="concept-empty">
                      <p>Concept preview unavailable.</p>
                      <span>{activeVisualization.error}</span>
                    </div>
                  ) : null}

                  {!activeVisualization || activeVisualization.status === 'idle' ? (
                    <div className="concept-empty">
                      <p>Concept preview not generated yet.</p>
                      <span>The selected idea will render here once the image model finishes.</span>
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="detail-grid">
                <section className="detail-card">
                  <p className="detail-kicker">Materials</p>
                  <ul className="tag-list">
                    {activeIdea.materials.map((material) => (
                      <li key={material}>{material}</li>
                    ))}
                  </ul>
                </section>

                <section className="detail-card">
                  <p className="detail-kicker">Difficulty</p>
                  <p className="detail-copy detail-copy--strong">{activeIdea.difficulty}</p>
                  <p className="detail-copy">{activeIdea.description}</p>
                </section>
              </div>

              <section className="steps-card">
                <p className="detail-kicker">How to make it</p>
                <ol className="step-list">
                  {activeIdea.steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              </section>

              <section className="links-card">
                <div className="links-heading">
                  <div>
                    <p className="detail-kicker">Related tutorials</p>
                    <p className="detail-copy">
                      {activeTutorialLinksState?.status === 'loading'
                        ? 'Refreshing grounded links for this idea…'
                        : 'Grounded to this exact idea when available, otherwise quick fallback links.'}
                    </p>
                  </div>
                </div>

                {activeTutorialLinksState?.status === 'loading' ? (
                  <div className="link-list">
                    <div className="skeleton-card skeleton-shimmer" style={{ height: '110px' }} />
                    <div className="skeleton-card skeleton-shimmer" style={{ height: '110px' }} />
                  </div>
                ) : (
                  <div className="link-list">
                    {activeTutorialLinks.map((link) => (
                      <a key={link.id} className="link-card" href={link.url} target="_blank" rel="noreferrer">
                        <div className="link-topline">
                          <span className={`source-pill source-pill--${link.source}`}>{link.source}</span>
                          <span className="link-arrow">Open ↗</span>
                        </div>
                        <h3>{link.title}</h3>
                        <p>{link.reason}</p>
                      </a>
                    ))}
                  </div>
                )}

                {activeTutorialLinksState?.status === 'error' ? (
                  <p className="status-message muted-message">{activeTutorialLinksState.error}</p>
                ) : null}
              </section>

              <p className="safety-note">Safety note: {result.safety_note}</p>
            </>
          ) : (
            <div className="empty-state">
              <p>No scan result yet.</p>
              <span>Once you submit a photo, the best reuse idea and concept preview will appear here.</span>
            </div>
          )}
        </article>
      </section>

      {isSubmitting ? (
        <section className="surface-card ideas-panel">
          <div className="section-heading">
            <div className="skeleton-text short skeleton-shimmer" style={{ marginBottom: '8px' }} />
            <div className="skeleton-title skeleton-shimmer" />
          </div>
          <div className="ideas-grid">
            <div className="skeleton-card skeleton-shimmer" />
            <div className="skeleton-card skeleton-shimmer" />
            <div className="skeleton-card skeleton-shimmer" />
            <div className="skeleton-card skeleton-shimmer" />
          </div>
        </section>
      ) : result ? (
        <section className="surface-card ideas-panel">
          <div className="section-heading">
            <p className="section-kicker">Alternatives</p>
            <h2>Other ways to reuse this object</h2>
          </div>

          <div className="ideas-grid">
            {result.ideas.map((idea, i) => {
              const isActive = activeIdea?.id === idea.id

              return (
                <button
                  key={idea.id}
                  type="button"
                  className={`idea-option ${isActive ? 'idea-option--active' : ''}`}
                  style={{ animationDelay: `${i * 60}ms` }}
                  onClick={() => selectIdea(idea)}
                >
                  <div className="idea-option-topline">
                    <span>Idea {idea.id.replace('idea_', '')}</span>
                    <span className="difficulty-pill">{idea.difficulty}</span>
                  </div>
                  <h3>{idea.title}</h3>
                  <p>{idea.description}</p>
                  <span className="idea-option-meta">{idea.tutorial_links.length} related links</span>
                </button>
              )
            })}
          </div>
        </section>
      ) : null}

      <section className="surface-card history-panel">
        <div className="section-heading">
          <p className="section-kicker">Local history</p>
          <h2>Recent scans on this browser</h2>
        </div>

        {history.length ? (
          <div className="history-grid">
            {history.map((entry, i) => (
              <button
                key={entry.scan_id}
                type="button"
                className="history-card"
                style={{ animationDelay: `${i * 50}ms` }}
                onClick={() => loadHistoryEntry(entry)}
              >
                <div className="history-topline">
                  <span>{entry.detected_label}</span>
                  <span>{Math.round(entry.confidence * 100)}%</span>
                </div>
                <h3>{entry.ideas[0]?.title ?? 'Reuse plan'}</h3>
                <p>{entry.summary}</p>
                <div className="history-footer">
                  <span>{new Date(entry.created_at).toLocaleString()}</span>
                  <span>{entry.source_mode}</span>
                </div>
              </button>
            ))}
          </div>
        ) : (
          <div className="empty-state compact">
            <p>No scans saved yet.</p>
            <span>Your last few scan results will stay in this browser for quick demos.</span>
          </div>
        )}
      </section>

      <details className="surface-card debug-panel">
        <summary>
          Debug flow
          <span>
            {selectedFile ? 'file loaded' : 'no file'} • {result ? 'result ready' : 'no result'} •{' '}
            {activeVisualization?.status ?? 'no preview'}
          </span>
        </summary>

        <div className="debug-state">
          <div className="debug-state-card">
            <p className="detail-kicker">Current state</p>
            <ul className="debug-list">
              <li>selectedFile: {selectedFile ? selectedFile.name : 'none'}</li>
              <li>scanStatus: {isSubmitting ? 'loading' : result ? 'ready' : 'idle'}</li>
              <li>sourceMode: {result?.source_mode ?? 'n/a'}</li>
              <li>providerState: {result?.provider_state ?? 'n/a'}</li>
              <li>providerNotice: {result?.provider_notice ?? 'none'}</li>
              <li>activeIdea: {activeIdea?.title ?? 'none'}</li>
              <li>visualization: {activeVisualization?.status ?? 'idle'}</li>
              <li>tutorialLinks: {activeTutorialLinksState?.status ?? 'idle'}</li>
              <li>scanTimings: {formatTimings(result?.timings_ms)}</li>
              <li>tutorialLinkTimings: {formatTimings(activeTutorialLinksState?.response?.timings_ms)}</li>
              <li>visualizationTimings: {formatTimings(activeVisualization?.response?.timings_ms)}</li>
            </ul>
          </div>

          <div className="debug-state-card">
            <p className="detail-kicker">Latest events</p>
            <ul className="debug-list">
              {debugEvents.length ? (
                debugEvents.map((event) => (
                  <li key={event.id}>
                    <strong>{event.timestamp}</strong> {event.message}
                  </li>
                ))
              ) : (
                <li>No events captured yet.</li>
              )}
            </ul>
          </div>
        </div>
      </details>
    </main>
  )
}

export default App
