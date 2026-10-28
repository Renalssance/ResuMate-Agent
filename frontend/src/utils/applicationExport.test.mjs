import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { registerHooks } from 'node:module'

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith('.') && context.parentURL?.endsWith('.ts') && !specifier.endsWith('.ts')) {
      return nextResolve(`${specifier}.ts`, context)
    }
    return nextResolve(specifier, context)
  },
})

const { createApplicationExportBlob } = await import('./applicationExport.ts')

const base = {
  resumeId: null,
  resumeFilename: '',
  appliedDate: '2026-10-11',
  status: 'applied',
  source: '官网',
  notes: '',
  schedules: [],
  createdAt: '2026-10-11T00:00:00Z',
  updatedAt: '2026-10-11T00:00:00Z',
}
const event = (id, status, hour, note = '') => ({
  id,
  status,
  changedAt: new Date(2026, 9, 11, hour, 30).toISOString(),
  note,
  createdAt: '2026-10-11T00:00:00Z',
})
const applications = [
  {
    ...base,
    id: 1,
    company: '坦信卫星',
    position: 'AI 大模型算法工程师',
    jobUrl: 'https://example.com/jobs/ai?source=官网&ref=校招',
    statusEvents: [event(2, 'first_interview', 14, '技术面试\n准备项目介绍'), event(1, 'applied', 8)],
  },
  {
    ...base,
    id: 2,
    company: '坦信卫星',
    position: '卫星通信系统工程师',
    jobUrl: 'https://example.com/jobs/satellite',
    statusEvents: [event(3, 'applied', 9)],
  },
  {
    ...base,
    id: 3,
    company: '商飞',
    position: 'AI 工程师',
    jobUrl: '',
    statusEvents: [],
  },
]

const blob = await createApplicationExportBlob(applications)
assert.equal(blob.type, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

// Read the generated XLSX independently to catch missing rows, swapped columns,
// escaped links, and lost or misordered timeline entries in the actual file.
const workbook = JSON.parse(execFileSync('python3', ['-c', `
import io, json, sys, zipfile
from xml.etree import ElementTree as ET

ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())) as archive:
    strings = ET.fromstring(archive.read('xl/sharedStrings.xml'))
    values = [''.join(node.itertext()) for node in strings.findall('s:si', ns)]
    sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
    rows = []
    for row in sheet.findall('s:sheetData/s:row', ns):
        cells = [''] * 4
        for cell in row.findall('s:c', ns):
            value = cell.find('s:v', ns)
            if value is not None:
                cells[ord(cell.attrib['r'][0]) - ord('A')] = values[int(value.text)]
        rows.append(cells)
    metadata = ET.fromstring(archive.read('xl/workbook.xml'))
    print(json.dumps({'rows': rows, 'sheet': metadata.find('s:sheets/s:sheet', ns).attrib['name']}, ensure_ascii=False))
`], { input: Buffer.from(await blob.arrayBuffer()), encoding: 'utf8' }))

assert.equal(workbook.sheet, '投递记录')
assert.deepEqual(workbook.rows, [
  ['公司名', '岗位', '投递链接', '投递时间线'],
  ['坦信卫星', 'AI 大模型算法工程师', 'https://example.com/jobs/ai?source=官网&ref=校招',
    '2026/10/11 08:30 · 已投\n2026/10/11 14:30 · 一面 · 技术面试\n准备项目介绍'],
  ['坦信卫星', '卫星通信系统工程师', 'https://example.com/jobs/satellite', '2026/10/11 09:30 · 已投'],
  ['商飞', 'AI 工程师', '', ''],
])
assert.deepEqual(applications[0].statusEvents.map(({ id }) => id), [2, 1], 'export must preserve the page timeline order')
console.log('Application XLSX export passed: columns, separate positions, links, and complete chronological timelines.')
