const BASE = "/api"

export class ApiError extends Error {
  status: number
  data: unknown
  constructor(status: number, data: unknown) {
    super(`API ${status}`)
    this.status = status
    this.data = data
  }
}

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"))
  return match ? decodeURIComponent(match[2]) : null
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase()
  const headers: Record<string, string> = { Accept: "application/json", ...(options.headers as Record<string, string>) }
  if (options.body) headers["Content-Type"] = "application/json"
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = getCookie("csrftoken")
    if (csrf) headers["X-CSRFToken"] = csrf
  }
  const res = await fetch(BASE + path, { credentials: "include", ...options, method, headers })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data)
  }
  if (res.status === 204) return null as T
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
}
