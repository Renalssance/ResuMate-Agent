/** Persist only accepted task IDs and display context; the server owns task state. */
export function activeTaskKey(kind: string) {
  return `resumate:active-${kind}:${localStorage.getItem('username') || ''}`
}
export function readActiveTask<T>(key: string): T | null {
  const raw = localStorage.getItem(key)
  if (!raw) return null
  try { return JSON.parse(raw) as T }
  catch { localStorage.removeItem(key); return null }
}
export function saveActiveTask(key: string, value: unknown) { localStorage.setItem(key, JSON.stringify(value)) }
