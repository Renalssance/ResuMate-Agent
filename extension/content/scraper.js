(() => {
  const hostname = location.hostname.toLowerCase();

  function text(selectors) {
    for (const selector of selectors.split(',')) {
      let element = null;
      try {
        element = document.querySelector(selector.trim());
      } catch (_error) {
        element = null;
      }
      const value = element && element.textContent ? element.textContent.trim().replace(/\s+/g, ' ') : '';
      if (value) return value.slice(0, 80);
    }
    return '';
  }

  function meta(name) {
    const element = document.querySelector(`meta[property="${name}"], meta[name="${name}"]`);
    return element ? (element.getAttribute('content') || '').trim() : '';
  }

  function genericPosition() {
    return text('h1, [class*="job-title"], [class*="jobTitle"], [class*="job-name"], [class*="positionName"], [class*="position-title"]');
  }

  function titleSegments(value) {
    return String(value || document.title).split(/\s*[|｜\-–—_·»【】]\s*/).map((item) => item.trim()).filter(Boolean);
  }

  function titlePosition(value) {
    const segments = titleSegments(value).filter((item) => !/招聘|校招|社招|Careers?|Jobs?|Hiring/i.test(item));
    return (segments.sort((a, b) => b.length - a.length)[0] || '').slice(0, 80);
  }

  function titleCompany(value) {
    for (const segment of titleSegments(value)) {
      if (/招聘|校招|社招|Careers?|Jobs?|Hiring/i.test(segment)) {
        const cleaned = segment.replace(/招聘|校招|社招|Careers?|Jobs?|Hiring/gi, '').replace(/官网|首页/g, '').trim();
        if (cleaned) return cleaned.slice(0, 40);
      }
    }
    return '';
  }

  const rules = [
    { match: (host) => host === 'jobs.bytedance.com', company: 'ByteDance', position: () => text('h1, [class*="postTitle"]') || genericPosition() },
    { match: (host) => host === 'careers.tencent.com' || host === 'join.qq.com', company: 'Tencent', position: () => text('.job-detail-title, h1') || genericPosition() },
    { match: (host) => host === 'talent.alibaba.com', company: 'Alibaba', position: genericPosition },
    { match: (host) => host === 'zhaopin.meituan.com', company: 'Meituan', position: genericPosition },
    { match: (host) => host === 'talent.baidu.com', company: 'Baidu', position: genericPosition },
    { match: (host) => host === 'careers.jd.com' || host === 'zhaopin.jd.com', company: 'JD', position: genericPosition },
    { match: (host) => host === 'hr.163.com' || host === 'campus.163.com', company: 'NetEase', position: genericPosition },
    { match: (host) => host === 'careers.pinduoduo.com', company: 'Pinduoduo', position: genericPosition },
    { match: (host) => host.endsWith('.mokahr.com'), company: () => meta('og:site_name') || titleCompany(), position: genericPosition },
    { match: (host) => host.endsWith('.beisen.com') || host.includes('hotjob'), company: () => meta('og:site_name') || titleCompany(), position: genericPosition },
    { match: (host) => host.endsWith('.myworkdayjobs.com'), company: (host) => host.split('.')[0], position: () => text('h1[data-automation-id="jobPostingHeader"], h1') },
    { match: (host) => host.endsWith('.greenhouse.io'), company: () => meta('og:site_name') || titleCompany(), position: () => text('h1.app-title, h1') },
    { match: (host) => host.endsWith('.lever.co'), company: () => meta('og:site_name') || titleCompany() || location.pathname.split('/').filter(Boolean)[0] || '', position: () => text('.posting-headline h2, h2, h1') }
  ];

  let company = '';
  let position = '';
  const confidence = { company: 'none', position: 'none' };
  const rule = rules.find((item) => item.match(hostname));
  if (rule) {
    company = typeof rule.company === 'function' ? rule.company(hostname) : rule.company;
    position = typeof rule.position === 'function' ? rule.position(hostname) : rule.position;
    if (company) confidence.company = 'site-rule';
    if (position) confidence.position = 'site-rule';
  }
  if (!company) {
    company = meta('og:site_name') || titleCompany() || hostname.split('.').filter((part) => !['www', 'careers', 'jobs', 'com', 'cn', 'net'].includes(part)).pop() || hostname;
    confidence.company = company ? 'fallback' : 'none';
  }
  if (!position) {
    position = titlePosition(meta('og:title')) || titlePosition() || genericPosition();
    confidence.position = position ? 'fallback' : 'none';
  }

  return { company, position, url: location.href, title: document.title, confidence };
})();
