const http = require('http');

const profile = {
  id: 'resume:demo',
  name: 'Ada Lovelace Demo',
  sourceResumeId: 'resume:demo',
  updatedAt: new Date().toISOString(),
  sections: [
    {
      id: 'basic',
      label: 'Basic',
      fields: [
        { key: 'candidate_name', label: 'Name', value: 'Ada Lovelace', aliases: ['姓名', 'full name'], category: 'basic', confidence: 'high', source: 'mock' },
        { key: 'contact.email', label: 'Email', value: 'ada@example.com', aliases: ['邮箱', 'email address'], category: 'basic', confidence: 'high', source: 'mock' },
        { key: 'contact.phone', label: 'Phone', value: '13800000000', aliases: ['手机', 'mobile'], category: 'basic', confidence: 'high', source: 'mock' },
        { key: 'contact.location', label: 'City', value: 'Shanghai', aliases: ['城市', 'city'], category: 'basic', confidence: 'high', source: 'mock' },
      ],
    },
    {
      id: 'education',
      label: 'Education',
      fields: [
        { key: 'education.0.school', label: 'School 1', value: 'Example University', aliases: ['学校', 'university'], category: 'education', confidence: 'high', source: 'mock' },
        { key: 'education.0.major', label: 'Major 1', value: 'Computer Science', aliases: ['专业', 'major'], category: 'education', confidence: 'high', source: 'mock' },
      ],
    },
    {
      id: 'skills',
      label: 'Skills',
      fields: [
        { key: 'skills', label: 'Skills', value: 'Python, FastAPI, Vue, Browser Automation', aliases: ['技能', 'technical skills'], category: 'skills', confidence: 'high', source: 'mock' },
      ],
    },
  ],
};

function profileFields() {
  return profile.sections.flatMap((section) => section.fields);
}

function elementText(element) {
  return [
    element.type,
    element.id,
    element.name,
    element.placeholder,
    element.labelText,
    element.ariaLabel,
    element.nearbyText,
  ].filter(Boolean).join(' ').toLowerCase();
}

function matchElements(elements) {
  const rules = [
    ['candidate_name', ['姓名', 'name']],
    ['contact.email', ['邮箱', 'email']],
    ['contact.phone', ['手机', 'mobile', 'phone', 'tel']],
    ['education.0.school', ['学校', 'school', 'university']],
    ['education.0.major', ['专业', 'major']],
    ['skills', ['技能', 'skills']],
    ['contact.location', ['城市', 'city']],
  ];
  const fieldsByKey = Object.fromEntries(profileFields().map((field) => [field.key, field]));
  const blocked = [];
  const matches = [];
  const used = new Set();

  for (const element of elements || []) {
    const text = elementText(element);
    if (text.includes('验证码') || text.includes('captcha') || element.type === 'password') {
      blocked.push({ elementIndex: element.index, reason: 'sensitive field', element });
      continue;
    }
    for (const [key, words] of rules) {
      if (used.has(key)) continue;
      if (words.some((word) => text.includes(word.toLowerCase()))) {
        matches.push({
          fieldKey: key,
          elementIndex: element.index,
          confidence: 'high',
          reason: 'mock keyword match',
          field: fieldsByKey[key],
          element,
        });
        used.add(key);
        break;
      }
    }
  }

  return { matches, blocked, warnings: [] };
}

function send(response, status, data) {
  response.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  });
  response.end(JSON.stringify(data));
}

http.createServer((request, response) => {
  if (request.method === 'OPTIONS') {
    send(response, 200, { ok: true });
    return;
  }

  const url = decodeURIComponent((request.url || '').split('?')[0]);
  if (request.method === 'GET' && url === '/api/autofill/profiles') {
    send(response, 200, [{
      id: profile.id,
      name: profile.name,
      sourceResumeId: profile.sourceResumeId,
      updatedAt: profile.updatedAt,
      fieldCount: profileFields().length,
    }]);
    return;
  }

  if (request.method === 'POST' && url === '/auth/login') {
    let body = '';
    request.on('data', (chunk) => {
      body += chunk;
    });
    request.on('end', () => {
      const payload = JSON.parse(body || '{}');
      if (!payload.username || !payload.password) {
        send(response, 401, { detail: 'username and password required' });
        return;
      }
      send(response, 200, {
        access_token: 'mock-jwt',
        token_type: 'bearer',
        username: payload.username,
        role: 'user',
      });
    });
    return;
  }

  if (request.method === 'GET' && url === '/api/autofill/profiles/resume:demo') {
    send(response, 200, profile);
    return;
  }

  if (request.method === 'POST' && url === '/api/autofill/match') {
    let body = '';
    request.on('data', (chunk) => {
      body += chunk;
    });
    request.on('end', () => {
      const payload = JSON.parse(body || '{}');
      send(response, 200, matchElements(payload.elements || []));
    });
    return;
  }

  if (request.method === 'POST' && url === '/api/autofill/events') {
    send(response, 200, { ok: true });
    return;
  }

  send(response, 404, { detail: 'not found' });
}).listen(8898, '127.0.0.1', () => {
  console.log('mock autofill api on http://127.0.0.1:8898');
});
