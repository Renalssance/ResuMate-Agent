import type { DocumentType } from '../types/document'

export function createTextUploadFile(type: DocumentType, text: string, now = () => new Date()): File {
  const content = text.trim()
  if (!content) throw new Error('请输入要上传的文本')
  const timestamp = now().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, '').replace('T', '-')
  return new File([content], `${type}-text-${timestamp}.txt`, { type: 'text/plain;charset=utf-8' })
}
