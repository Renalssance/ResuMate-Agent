import { describe, expect, it } from 'vitest'
import { parseSseStream, type SseFrame } from './sseParser'

function responseFromChunks(chunks: Uint8Array[]) {
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk)
      controller.close()
    },
  }))
}

const encoder = new TextEncoder()

describe('parseSseStream', () => {
  it('preserves UTF-8, CRLF, multiline data and ids across network fragments', async () => {
    const frames: SseFrame[] = []
    const bytes = encoder.encode(': heartbeat\r\n\r\nevent: run.event\r\nid: 7\r\ndata: 你好\r\ndata: next\r\n\r\ndata: final\n\n')
    await parseSseStream(responseFromChunks(Array.from(bytes, (byte) => new Uint8Array([byte]))), (frame) => frames.push(frame))
    expect(frames).toEqual([
      { event: 'run.event', id: '7', data: '你好\nnext' },
      { event: 'message', id: '7', data: 'final' },
    ])
  })

  it('discards an unfinished frame when the connection ends', async () => {
    const frames: SseFrame[] = []
    await parseSseStream(responseFromChunks([encoder.encode('data: complete\n\ndata: partial\n')]), (frame) => frames.push(frame))
    expect(frames).toEqual([{ event: 'message', data: 'complete' }])
  })

  it('cancels a blocked reader on abort without dispatching buffered data', async () => {
    const frames: SseFrame[] = []
    const abort = new AbortController()
    let cancelled = false
    const response = new Response(new ReadableStream<Uint8Array>({
      start(controller) { controller.enqueue(encoder.encode('data: partial')) },
      cancel() { cancelled = true },
    }))
    const done = parseSseStream(response, (frame) => frames.push(frame), abort.signal)
    abort.abort()
    await done
    expect(cancelled).toBe(true)
    expect(frames).toEqual([])
    expect(response.body?.locked).toBe(false)
  })

  it('releases the reader when the consumer stops after a frame', async () => {
    const response = responseFromChunks([encoder.encode('data: first\n\ndata: second\n\n')])
    const stop = new Error('stop')
    await expect(parseSseStream(response, () => { throw stop })).rejects.toBe(stop)
    expect(response.body?.locked).toBe(false)
  })
})
