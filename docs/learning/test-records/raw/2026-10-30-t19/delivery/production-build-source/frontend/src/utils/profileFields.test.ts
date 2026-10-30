// @ts-expect-error Node's strip-types runner imports the TypeScript source directly.
const { profileRequiredFields, countFilledProfileFields, valueAtProfilePath } = await import('./profileFields.ts')

export {}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

const profile = {
  candidate_name: '朱皆霖',
  contact: {
    email: 'grandZJL@outlook.com',
    phone: '15951419875',
  },
  application: {
    gender: '男',
  },
}

assert(
  profileRequiredFields.some((item: { label: string; path: string }) => item.label === '姓名' && item.path === 'candidate_name'),
  'profile fields should keep the recruiting system path beside the Chinese label',
)
assert(
  valueAtProfilePath(profile, 'contact.email') === 'grandZJL@outlook.com',
  'profile field paths should read nested recruiting values',
)
assert(
  countFilledProfileFields(profile) === 4,
  'profile filled count should use the shared recruiting field list',
)
