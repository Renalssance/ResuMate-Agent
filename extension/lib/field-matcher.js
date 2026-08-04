const SENSITIVE = [
  'password',
  'captcha',
  'verification',
  'verify code',
  'sms code',
  'one-time',
  'otp',
  'id card',
  'identity card',
  'national id',
  'bank card',
  'credit card',
  '\u5bc6\u7801',
  '\u9a8c\u8bc1\u7801',
  '\u6821\u9a8c\u7801',
  '\u8eab\u4efd\u8bc1',
  '\u94f6\u884c\u5361'
];

const KEYWORDS = {
  candidate_name: ['name', 'full name', '\u59d3\u540d', '\u540d\u5b57'],
  'contact.email': ['email', 'e-mail', '\u90ae\u7bb1', '\u7535\u5b50\u90ae\u7bb1'],
  'contact.phone': ['phone', 'mobile', 'tel', 'telephone', '\u624b\u673a', '\u7535\u8bdd'],
  'contact.location': ['city', 'location', 'current city', '\u57ce\u5e02', '\u6240\u5728\u5730'],
  skills: ['skills', 'technical skills', '\u6280\u80fd', '\u4e13\u4e1a\u6280\u80fd'],
  languages: ['languages', 'language', '\u8bed\u8a00'],
  certifications: ['certifications', 'certificate', '\u8bc1\u4e66'],
  self_summary: ['summary', 'self introduction', 'about me', '\u81ea\u6211\u4ecb\u7ecd', '\u4e2a\u4eba\u4ecb\u7ecd']
};

export function norm(value) {
  return String(value || '').toLowerCase().replace(/\s+/g, ' ').trim();
}

export function elementText(element) {
  const parts = [
    element.type,
    element.id,
    element.name,
    element.placeholder,
    element.labelText,
    element.ariaLabel,
    element.nearbyText
  ];
  return norm(parts.filter(Boolean).join(' '));
}

export function fieldKeywords(field) {
  const keywords = [field.key, field.label, ...(field.aliases || []), ...(KEYWORDS[field.key] || [])];
  if (field.key.startsWith('education.') && field.key.endsWith('.school')) keywords.push('school', 'university', '\u5b66\u6821');
  if (field.key.startsWith('education.') && field.key.endsWith('.major')) keywords.push('major', '\u4e13\u4e1a');
  if (field.key.startsWith('education.') && field.key.endsWith('.degree')) keywords.push('degree', '\u5b66\u4f4d');
  if (field.key.startsWith('work_experience.') && field.key.endsWith('.company')) keywords.push('company', 'employer', '\u516c\u53f8');
  if (field.key.startsWith('work_experience.') && field.key.endsWith('.title')) keywords.push('title', 'role', 'position', '\u5c97\u4f4d');
  if (field.key.endsWith('.description')) keywords.push('description', 'details', '\u4ecb\u7ecd', '\u63cf\u8ff0', '\u804c\u8d23');
  return keywords.map(norm).filter(Boolean);
}

export function isSensitive(element) {
  const text = elementText(element);
  if (norm(element.type) === 'password') return true;
  return SENSITIVE.some((pattern) => text.includes(pattern));
}

export function flattenFields(profile) {
  if (!profile || !Array.isArray(profile.sections)) return [];
  return profile.sections.flatMap((section) => {
    if (!Array.isArray(section.fields)) return [];
    return section.fields;
  });
}

function scoreFieldForElement(field, element) {
  const text = elementText(element);
  if (!text || !field.value) return { score: 0, reason: '' };
  let best = 0;
  let reason = '';
  for (const keyword of fieldKeywords(field)) {
    if (keyword === text) return { score: 100, reason: `exact match on "${keyword}"` };
    if (text.includes(keyword) && keyword.length > best) {
      best = keyword.length;
      reason = `label contains "${keyword}"`;
    }
  }
  return { score: best, reason };
}

export function matchLocally(profile, elements) {
  const fields = flattenFields(profile).filter((field) => field.value);
  const blocked = [];
  const candidates = [];

  for (const element of elements || []) {
    if (isSensitive(element)) {
      blocked.push({
        elementIndex: element.index,
        reason: 'sensitive field',
        element
      });
      continue;
    }

    for (const field of fields) {
      const scored = scoreFieldForElement(field, element);
      if (scored.score > 0) {
        candidates.push({
          score: scored.score,
          elementIndex: element.index,
          field,
          element,
          reason: scored.reason
        });
      }
    }
  }

  const matches = [];
  const usedFields = new Set();
  const usedElements = new Set();
  candidates.sort((left, right) => right.score - left.score);

  for (const candidate of candidates) {
    if (usedFields.has(candidate.field.key) || usedElements.has(candidate.elementIndex)) continue;
    matches.push({
      fieldKey: candidate.field.key,
      elementIndex: candidate.elementIndex,
      confidence: candidate.score >= 2 ? 'high' : 'medium',
      reason: candidate.reason,
      field: candidate.field,
      element: candidate.element
    });
    usedFields.add(candidate.field.key);
    usedElements.add(candidate.elementIndex);
  }

  return {
    matches: matches.sort((left, right) => left.elementIndex - right.elementIndex),
    blocked,
    warnings: []
  };
}
