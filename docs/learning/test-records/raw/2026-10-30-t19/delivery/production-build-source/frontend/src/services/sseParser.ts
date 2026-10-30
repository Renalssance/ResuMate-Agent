export interface SseFrame {
  event: string
  data: string
  id?: string
}

/** Decode complete SSE frames; an interrupted frame is replayed on reconnect. */
export async function parseSseStream(
  response: Response,
  onFrame: (frame: SseFrame) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (!response.body) throw new Error('SSE response has no body')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let event = ''
  let id: string | undefined
  let data: string[] = []
  const cancel = () => { void reader.cancel().catch(() => {}) }

  function consume(text: string, eof = false) {
    buffer += text
    while (!signal?.aborted) {
      const index = buffer.search(/[\r\n]/)
      if (index < 0 || (!eof && index === buffer.length - 1 && buffer[index] === '\r')) return
      const line = buffer.slice(0, index)
      const separatorLength = buffer[index] === '\r' && buffer[index + 1] === '\n' ? 2 : 1
      buffer = buffer.slice(index + separatorLength)
      if (line === '') {
        if (data.length) onFrame({ event: event || 'message', data: data.join('\n'), ...(id === undefined ? {} : { id }) })
        event = ''
        data = []
        continue
      }
      if (line.startsWith(':')) continue
      const colon = line.indexOf(':')
      const field = colon < 0 ? line : line.slice(0, colon)
      const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '')
      if (field === 'event') event = value
      else if (field === 'data') data.push(value)
      else if (field === 'id') id = value
    }
  }

  signal?.addEventListener('abort', cancel, { once: true })
  try {
    while (!signal?.aborted) {
      const { done, value } = await reader.read()
      if (signal?.aborted) return
      if (done) {
        consume(decoder.decode(), true)
        return
      }
      consume(decoder.decode(value, { stream: true }))
    }
  } catch (error) {
    if (!signal?.aborted) throw error
  } finally {
    signal?.removeEventListener('abort', cancel)
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
