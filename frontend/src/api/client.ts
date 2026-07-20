export const API_KEY = import.meta.env.VITE_API_KEY as string

export interface Zone {
  zone_id: string
  name: string
  lat: number
  lon: number
  status: 'active' | 'inactive'
  description?: string
}

export interface HealthResponse {
  status: string
  service: string
}

export interface AnalyseResponse {
  zone_id: string
  summary: string
  details?: string
  timestamp?: string
  [key: string]: unknown
}

export interface CompareResult {
  zone_id: string
  summary?: string
  details?: string
  error?: string
  status?: string
  [key: string]: unknown
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatResponse {
  reply: string
}

class ApiError extends Error {
  public status: number;
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  signal?: AbortSignal
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.method !== 'GET' ? { 'X-API-Key': API_KEY } : {}),
    ...(options.headers as Record<string, string> ?? {}),
  }

  const res = await fetch(path, { ...options, headers, signal })

  if (!res.ok) {
    throw new ApiError(res.status, `${res.status} ${res.statusText}`)
  }

  return res.json() as Promise<T>
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>('/health', { method: 'GET' }, signal)
}

export async function getZones(signal?: AbortSignal): Promise<Zone[]> {
  const data = await request<{ zones: Zone[] }>('/zones', { method: 'GET' }, signal)
  return data.zones
}

export async function postAnalyse(
  zoneId: string,
  prompt: string,
  lat?: number,
  lon?: number,
  signal?: AbortSignal
): Promise<AnalyseResponse> {
  const data = await request<any>(
    '/analyse',
    { 
      method: 'POST', 
      body: JSON.stringify({ 
        zone_id: zoneId, 
        prompt,
        ...(lat !== undefined ? { lat } : {}),
        ...(lon !== undefined ? { lon } : {})
      }) 
    },
    signal
  )

  const summary = data.biodiversity_insight || data.decision_brief?.judge_summary || 'No summary available.';
  const details = data.top_intervention 
    ? `Top Intervention:\n${data.top_intervention}\n\nAdditional Actions:\n${(data.pollination_boost_actions || []).map((a: string) => `- ${a}`).join('\n')}`
    : '';

  return {
    zone_id: zoneId,
    summary,
    details,
    timestamp: data.analysed_at || new Date().toISOString()
  }
}

export async function postCompare(
  zoneA: string,
  zoneB: string,
  signal?: AbortSignal
): Promise<CompareResult[]> {
  const data = await request<{ zones: any[] }>(
    '/compare',
    { method: 'POST', body: JSON.stringify({ zone_ids: [zoneA, zoneB] }) },
    signal
  )

  return data.zones.map(z => {
    if (z.status === 'error' || z.status === 'timeout') {
      return {
        zone_id: z.zone_id,
        status: z.status,
        error: z.error
      }
    }

    const summary = z.biodiversity_insight || z.decision_brief?.judge_summary || 'No summary available.';
    const details = z.top_intervention 
      ? `Top Intervention:\n${z.top_intervention}\n\nAdditional Actions:\n${(z.pollination_boost_actions || []).map((a: string) => `- ${a}`).join('\n')}`
      : '';

    return {
      ...z,
      summary,
      details
    }
  })
}

export async function postChat(
  message: string,
  history: ChatMessage[],
  signal?: AbortSignal
): Promise<ChatResponse> {
  return request<ChatResponse>(
    '/chat',
    { method: 'POST', body: JSON.stringify({ message, history }) },
    signal
  )
}

export { ApiError }
