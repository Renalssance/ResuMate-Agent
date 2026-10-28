// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { buildSearchIndex, matchesSearch } = await import('./search.ts')

export {}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

const company = buildSearchIndex(['字节跳动', '前端开发工程师', 'Boss直聘', '内推', '张三_简历2026.pdf'])
for (const query of ['字节', 'zijietiaodong', 'ZI JIE TIAO DONG', 'zjtd', 'qianduan', 'qd kf', 'BOSS', 'neitui', 'zhangsan', 'jl2026.pdf', '2026.pdf', '', '  ']) {
  assert(matchesSearch(company, query), `投递记录应匹配：${query}`)
}
assert(!matchesSearch(company, '腾讯'), '不应匹配无关中文')
assert(!matchesSearch(company, 'tengxun'), '不应匹配无关拼音')
assert(!matchesSearch(buildSearchIndex(['字节', '跳动']), 'zijietiaodong'), '不应跨字段拼接出搜索结果')

const document = buildSearchIndex(['候选人简历.docx', JSON.stringify({ school: '重庆大学', experience: '银行 Java 开发', name: '吕明' })])
for (const query of ['候选人', 'houxuanren', 'hxr', 'chongqing', '重庆大学', 'yinhang', 'java', 'lvming']) {
  assert(matchesSearch(document, query), `文档文件名或解析内容应匹配：${query}`)
}
assert(!matchesSearch(buildSearchIndex(['']), 'zhang'), '空内容不应匹配非空查询')
console.log('中文、拼音全拼、首字母及原有英文数字搜索测试通过')
