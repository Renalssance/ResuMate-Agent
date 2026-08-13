import { DEFAULT_API_BASE } from '../lib/constants.js';
import { normalizeLanguage, t } from '../lib/i18n.js';
import { getProfile, listProfiles, login as loginAccount, matchFields, recordEvent } from '../lib/api-client.js';
import { diagnoseMatches, matchLocally } from '../lib/field-matcher.js';
import {
  cacheProfiles,
  clearAuthSession,
  getActiveProfileId,
  getCachedProfiles,
  getLanguage,
  getSettings,
  setLanguage,
  saveSettings,
  saveAuthSession,
  setActiveProfileId
} from '../lib/storage.js';

const state = {
  apiBase: DEFAULT_API_BASE,
  token: '',
  username: '',
  profileSummaries: [],
  activeProfile: null,
  offline: false,
  matches: [],
  blocked: [],
  page: null,
  elements: [],
  scannedTabId: null,
  scannedTabUrl: '',
  scannedProfileId: '',
  scanStaleReason: '',
  scanStaleKey: '',
  statusText: 'Disconnected',
  statusKey: '',
  statusKindName: 'neutral',
  statusParams: {},
  language: 'en',
  debug: {
    lastAction: 'init',
    lastError: '',
    lastScanAt: '',
    localDiagnostics: null,
    matchResponse: null
  }
};

const $ = (id) => document.getElementById(id);

function settings() {
  return {
    apiBase: state.apiBase,
    token: state.token
  };
}

function activeProfileId() {
  return state.activeProfile ? state.activeProfile.id || '' : '';
}

function tr(key, params = {}) {
  return t(state.language, key, params);
}

function updateStaticText() {
  document.documentElement.lang = state.language === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-i18n]').forEach((element) => {
    element.textContent = tr(element.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach((element) => {
    element.placeholder = tr(element.dataset.i18nPlaceholder);
  });
  document.querySelectorAll('[data-i18n-aria-label]').forEach((element) => {
    element.setAttribute('aria-label', tr(element.dataset.i18nAriaLabel));
  });
  document.querySelectorAll('.lang-btn').forEach((button) => {
    const isActive = button.dataset.language === state.language;
    button.classList.toggle('is-active', isActive);
    button.setAttribute('aria-pressed', String(isActive));
  });
}

function setStatus(text) {
  state.statusText = text;
  state.statusKey = '';
  state.statusKindName = statusKind(text);
  state.statusParams = {};
  const statusText = $('statusText');
  statusText.textContent = humanStatus(text);
  statusText.dataset.rawStatus = text;
  statusText.className = `status-badge ${state.statusKindName}`;
  renderActionHint(text);
}

function setStatusKey(key, kind = 'warning', params = {}) {
  state.statusText = key;
  state.statusKey = key;
  state.statusKindName = kind;
  state.statusParams = params;
  const statusText = $('statusText');
  statusText.textContent = tr(key, params);
  statusText.dataset.rawStatus = key;
  statusText.className = `status-badge ${kind}`;
  renderActionHint(key);
}

function restoreStatus(defaultStatus) {
  if (state.scanStaleKey) {
    setStatusKey(state.scanStaleKey);
    return;
  }
  setStatus(defaultStatus);
}

function refreshStatusText() {
  if (state.statusKey) {
    setStatusKey(state.statusKey, state.statusKindName, state.statusParams);
    return;
  }
  setStatus(state.statusText);
}

function safeText(value, fallback = '') {
  return value === undefined || value === null || value === '' ? fallback : String(value);
}

function allFields(profile) {
  if (!profile || !Array.isArray(profile.sections)) return [];
  return profile.sections.flatMap((section) => {
    if (!Array.isArray(section.fields)) return [];
    return section.fields;
  });
}

function formatUpdatedAt(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
  return date.toLocaleDateString(state.language === 'zh' ? 'zh-CN' : 'en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  });
}

function renderSettings() {
  $('apiBaseInput').value = state.apiBase;
  $('usernameInput').value = state.username;
  if (state.token) $('passwordInput').value = '';
  $('logoutBtn').disabled = !state.token;
  $('loginBtn').disabled = false;
  const authStatus = $('authStatus');
  authStatus.textContent = state.token ? tr('auth.signedInAs', { username: state.username || tr('auth.account') }) : tr('auth.signedOut');
}

function renderProfiles() {
  const profileSelect = $('profileSelect');
  const options = state.profileSummaries.map((profile) => {
    const option = document.createElement('option');
    option.value = profile.id;
    const fieldCount = Number(profile.fieldCount ?? profile.field_count ?? 0);
    const updatedAt = formatUpdatedAt(profile.updatedAt || profile.updated_at);
    const meta = tr('resume.optionMeta', { count: fieldCount, updatedAt });
    option.textContent = `${profile.name || profile.id} - ${meta}`;
    return option;
  });

  profileSelect.replaceChildren(...options);
  profileSelect.disabled = options.length === 0;
  profileSelect.value = state.activeProfile ? state.activeProfile.id : '';

  const profileSummary = $('profileSummary');
  const fieldCount = state.activeProfile ? allFields(state.activeProfile).filter((field) => field.value).length : 0;
  if (!state.activeProfile) {
    profileSummary.textContent = state.profileSummaries.length ? tr('empty.noProfileLoaded') : tr('resume.noResumes');
  } else if (state.offline) {
    profileSummary.textContent = tr('resume.summaryOffline', { count: fieldCount });
  } else {
    profileSummary.textContent = tr('resume.summary', { count: fieldCount });
  }
}

function createFallbackProfileFields() {
  const fallback = document.createElement('div');
  fallback.className = 'empty-state';
  fallback.textContent = state.profileSummaries.length ? tr('resume.emptyPreview') : tr('resume.noResumes');
  return [fallback];
}

function createProfileField(field) {
  const container = document.createElement('div');
  container.className = 'field';

  const label = document.createElement('strong');
  label.className = 'field-title';
  label.textContent = field.label || field.key || tr('field.default');

  const value = document.createElement('div');
  value.className = 'field-value';
  value.textContent = field.value || '';

  container.append(label, value);
  return container;
}

function renderFields() {
  const profileFields = $('profileFields');
  const fields = state.activeProfile
    ? allFields(state.activeProfile)
        .filter((field) => field.value)
        .slice(0, 12)
        .map(createProfileField)
    : createFallbackProfileFields();

  profileFields.replaceChildren(...fields);
}

function matchFieldKey(match) {
  return match.fieldKey || match.field_key || '';
}

function matchElementIndex(match) {
  return Number(match.elementIndex ?? match.element_index);
}

function humanStatus(text) {
  const value = safeText(text, 'Disconnected');
  const lower = value.toLowerCase();
  if (lower === 'connected') return tr('status.connected');
  if (lower === 'offline') return tr('status.offline');
  if (lower === 'disconnected') return tr('status.disconnected');
  if (lower.includes('connecting')) return tr('status.connecting');
  if (lower.includes('scanning')) return tr('status.scanning');
  if (lower.includes('matches ready')) return tr('status.matchesReady');
  if (lower.includes('offline matches ready')) return tr('status.offlineMatchesReady');
  if (lower.includes('filling')) return tr('status.filling');
  if (lower.includes('filled') && lower.includes('failed')) {
    const counts = value.match(/Filled\s+(\d+),\s+failed\s+(\d+)/i);
    return counts ? tr('status.filledPartial', { success: counts[1], failed: counts[2] }) : value;
  }
  if (lower.includes('filled')) {
    const count = Number((value.match(/Filled\s+(\d+)/i) || [])[1] || 0);
    return tr('status.filled', { count, plural: count === 1 ? '' : 's' });
  }
  if (lower.includes('failed') || lower.includes('error')) return tr('status.needsAttention');
  return value;
}

function statusKind(text) {
  const lower = safeText(text).toLowerCase();
  if ((lower.includes('failed') && !lower.includes('failed 0')) || lower.includes('error') || lower.includes('disconnected')) return 'danger';
  if (lower.includes('offline') || lower.includes('no profile') || lower.includes('scan again') || lower.includes('select')) return 'warning';
  if (lower.includes('connecting') || lower.includes('scanning') || lower.includes('filling') || lower.includes('loading')) return 'busy';
  if (lower.includes('connected') || lower.includes('ready') || lower.includes('filled')) return 'success';
  return 'neutral';
}

function renderActionHint(statusText = state.statusText) {
  const actionHint = $('actionHint');
  if (!actionHint) return;

  const selected = document.querySelectorAll('#matches input[type="checkbox"]:checked').length;
  if (!state.activeProfile) {
    actionHint.textContent = tr('hint.loadProfileBeforeScanning');
  } else if (state.scannedProfileId && state.scannedProfileId !== activeProfileId()) {
    actionHint.textContent = tr('hint.profileChanged');
  } else if (state.scanStaleKey) {
    actionHint.textContent = tr(state.scanStaleKey);
  } else if (state.scanStaleReason) {
    actionHint.textContent = state.scanStaleReason;
  } else if (state.scannedTabId === null) {
    actionHint.textContent = tr('hint.scanPreview');
  } else if (state.matches.length === 0) {
    actionHint.textContent = tr('hint.noFillableFields');
  } else if (selected === 0) {
    actionHint.textContent = tr('hint.selectAtLeastOne');
  } else if (safeText(statusText).toLowerCase().includes('url changed')) {
    actionHint.textContent = tr('status.pageChanged');
  } else {
    actionHint.textContent = tr('hint.readyToFill', { count: selected, plural: selected === 1 ? '' : 's' });
  }
}

function renderPageInfo() {
  const pageInfo = $('pageInfo');
  if (!state.page) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = state.activeProfile ? tr('empty.scanBeforeFill') : tr('empty.loadProfileThenScan');
    pageInfo.replaceChildren(empty);
    return;
  }

  const title = document.createElement('p');
  title.className = 'page-title';
  title.textContent = safeText(state.page.title || state.page.url, tr('page.current'));

  const subtitle = document.createElement('p');
  subtitle.className = 'muted';
  subtitle.textContent = `${safeText(state.page.company, tr('page.unknownCompany'))} / ${safeText(state.page.position, tr('page.unknownPosition'))}`;

  const metrics = document.createElement('div');
  metrics.className = 'metrics';

  const metricData = [
    [tr('metrics.detected'), state.elements.length],
    [tr('metrics.ready'), state.matches.length],
    [tr('metrics.skipped'), state.blocked.length]
  ];
  const metricNodes = metricData.map(([label, value]) => {
    const node = document.createElement('div');
    node.className = 'metric';
    const strong = document.createElement('strong');
    strong.textContent = String(value);
    const span = document.createElement('span');
    span.textContent = label;
    node.append(strong, span);
    return node;
  });
  metrics.append(...metricNodes);

  pageInfo.replaceChildren(title, subtitle, metrics);
}

function createEmptyMatches(text) {
  const empty = document.createElement('div');
  empty.className = 'empty-state';
  empty.textContent = text;
  return [empty];
}

function createMatchRow(match, rowIndex) {
  const row = document.createElement('label');
  row.className = 'match is-selected';

  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.checked = true;
  checkbox.value = String(rowIndex);
  checkbox.addEventListener('change', () => {
    row.classList.toggle('is-selected', checkbox.checked);
    updateFillButtonState();
  });

  const details = document.createElement('div');

  const title = document.createElement('strong');
  title.className = 'match-title';
  const fieldLabel = match.field ? safeText(match.field.label || match.field.key, tr('field.default')) : tr('field.default');
  const element = match.element || {};
  const elementLabel = element.labelText || element.placeholder || element.name || element.id || tr('match.element', { index: matchElementIndex(match) });
  title.textContent = `${elementLabel} -> ${fieldLabel}`;

  const value = document.createElement('div');
  value.className = 'match-value';
  value.textContent = match.field ? safeText(match.field.value) : '';

  const reason = document.createElement('div');
  reason.className = 'match-reason';
  reason.textContent = safeText(match.reason || match.confidence, tr('match.defaultReason'));

  details.append(title, value, reason);
  row.append(checkbox, details);
  return row;
}

function blockedElementIndex(blocked) {
  return Number(blocked.elementIndex ?? blocked.element_index);
}

function createBlockedRow(blocked) {
  const row = document.createElement('div');
  row.className = 'match blocked';

  const icon = document.createElement('span');
  icon.className = 'blocked-icon';
  icon.textContent = '!';

  const details = document.createElement('div');
  const element = blocked.element || {};
  const elementLabel = element.labelText || element.placeholder || element.name || element.id || tr('match.element', { index: blockedElementIndex(blocked) });

  const title = document.createElement('strong');
  title.className = 'match-title';
  title.textContent = tr('match.blockedTitle', { label: elementLabel });

  const reason = document.createElement('div');
  reason.className = 'match-reason';
  reason.textContent = safeText(blocked.reason, tr('match.blockedFallback'));

  details.append(title, reason);
  row.append(icon, details);
  return row;
}

function renderMatches() {
  const matchesContainer = $('matches');
  const matches = Array.isArray(state.matches) ? state.matches : [];
  const blocked = Array.isArray(state.blocked) ? state.blocked : [];
  const rows = [
    ...(matches.length ? matches.map(createMatchRow) : createEmptyMatches(tr('empty.noMatches'))),
    ...blocked.map(createBlockedRow)
  ];
  matchesContainer.replaceChildren(...rows);
  updateFillButtonState();
}

function debugFields() {
  return allFields(state.activeProfile).map((field) => ({
    key: field.key,
    label: field.label,
    hasValue: Boolean(field.value),
    valuePreview: safeText(field.value).slice(0, 80),
    aliases: Array.isArray(field.aliases) ? field.aliases : []
  }));
}

function debugElements() {
  return (state.elements || []).map((element) => ({
    index: element.index,
    tag: element.tag,
    type: element.type,
    id: element.id,
    name: element.name,
    placeholder: element.placeholder,
    labelText: element.labelText,
    ariaLabel: element.ariaLabel,
    nearbyText: element.nearbyText,
    valuePresent: Boolean(element.value)
  }));
}

function debugMatches() {
  return (state.matches || []).map((match) => ({
    fieldKey: matchFieldKey(match),
    elementIndex: matchElementIndex(match),
    confidence: match.confidence,
    reason: match.reason,
    elementLabel: match.element ? match.element.labelText || match.element.placeholder || match.element.name || '' : '',
    valuePreview: match.field ? safeText(match.field.value).slice(0, 80) : ''
  }));
}

function debugBlocked() {
  return (state.blocked || []).map((blocked) => ({
    elementIndex: blockedElementIndex(blocked),
    reason: blocked.reason,
    elementLabel: blocked.element ? blocked.element.labelText || blocked.element.placeholder || blocked.element.name || '' : ''
  }));
}

function renderDebug() {
  const debugSummary = $('debugSummary');
  const debugOutput = $('debugOutput');
  if (!debugSummary || !debugOutput) return;

  const localDiagnostics = state.activeProfile && state.elements.length ? diagnoseMatches(state.activeProfile, state.elements) : null;
  state.debug.localDiagnostics = localDiagnostics;

  const payload = {
    lastAction: state.debug.lastAction,
    lastError: state.debug.lastError,
    lastScanAt: state.debug.lastScanAt,
    mode: state.offline ? 'offline-local-match' : 'online-api-match',
    apiBase: state.apiBase,
    authenticated: Boolean(state.token),
    activeProfileId: activeProfileId(),
    page: state.page,
    counts: {
      profileFields: debugFields().length,
      profileFieldsWithValue: debugFields().filter((field) => field.hasValue).length,
      detectedElements: state.elements.length,
      backendMatches: state.matches.length,
      blocked: state.blocked.length,
      localDiagnosticCandidates: localDiagnostics ? localDiagnostics.elements.filter((item) => item.status === 'candidate').length : 0
    },
    detectedElements: debugElements(),
    profileFields: debugFields(),
    backendMatches: debugMatches(),
    backendBlocked: debugBlocked(),
    localDiagnostics: localDiagnostics
      ? localDiagnostics.elements.map((item) => ({
          index: item.element.index,
          status: item.status,
          elementText: item.elementText,
          bestCandidate: item.bestCandidate,
          candidates: item.candidates
        }))
      : []
  };

  debugSummary.textContent = `elements=${payload.counts.detectedElements} backendMatches=${payload.counts.backendMatches} localCandidates=${payload.counts.localDiagnosticCandidates} error=${payload.lastError || 'none'}`;
  debugOutput.textContent = JSON.stringify(payload, null, 2);
}

function updateFillButtonState() {
  const selected = document.querySelectorAll('#matches input[type="checkbox"]:checked').length;
  const profileChanged = Boolean(state.scannedProfileId && state.scannedProfileId !== activeProfileId());
  $('fillBtn').disabled = state.matches.length === 0 || state.scannedTabId === null || selected === 0 || Boolean(state.scanStaleReason) || profileChanged;
  renderActionHint();
}

function markScanStale(key) {
  if (state.scannedTabId === null && state.scanStaleKey === key) return;
  state.scanStaleKey = key;
  state.scanStaleReason = tr(key);
  state.scannedTabId = null;
  state.scannedTabUrl = '';
  setStatusKey(key);
  updateFillButtonState();
}

function clearScanForProfileChange(key = 'status.profileChanged') {
  if (state.matches.length === 0 && state.blocked.length === 0 && state.scannedTabId === null) return;
  state.matches = [];
  state.blocked = [];
  state.elements = [];
  state.page = null;
  state.scannedTabId = null;
  state.scannedTabUrl = '';
  state.scannedProfileId = '';
  state.scanStaleKey = key;
  state.scanStaleReason = tr(key);
  renderPageInfo();
  renderMatches();
  setStatusKey(key);
}

function render() {
  updateStaticText();
  renderSettings();
  renderProfiles();
  renderFields();
  renderPageInfo();
  renderMatches();
  renderDebug();
}

async function changeLanguage(language) {
  state.language = normalizeLanguage(language);
  await setLanguage(state.language);
  if (state.scanStaleKey) state.scanStaleReason = tr(state.scanStaleKey);
  render();
  refreshStatusText();
}

async function activeTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0] || null;
}

async function loadProfile(profileId, options = {}) {
  if (options.invalidateExistingScan) {
    clearScanForProfileChange(options.reasonKey || 'status.profileRefreshed');
  }

  if (!profileId) {
    state.activeProfile = null;
    clearScanForProfileChange();
    await setActiveProfileId('');
    render();
    return;
  }

  const previousProfileId = activeProfileId();
  const profile = await getProfile(settings(), profileId);
  state.activeProfile = profile;
  await setActiveProfileId(profile.id || profileId);
  if (previousProfileId && previousProfileId !== activeProfileId()) clearScanForProfileChange();
  render();
}

function summarizeProfile(profile) {
  return {
    id: profile.id,
    name: profile.name || profile.id
  };
}

function summarizeElement(element) {
  return {
    index: element.index,
    tag: safeText(element.tag),
    type: safeText(element.type),
    name: safeText(element.name).slice(0, 80),
    labelText: safeText(element.labelText).slice(0, 120),
    placeholder: safeText(element.placeholder).slice(0, 120)
  };
}

function pageFromTab(tab) {
  return {
    url: tab && tab.url ? tab.url : '',
    title: tab && tab.title ? tab.title : '',
    company: '',
    position: '',
    confidence: {}
  };
}

async function recordSafely(payload) {
  if (state.offline) return;
  try {
    await recordEvent(settings(), payload);
  } catch (_error) {
    // Telemetry must not block user-controlled filling.
  }
}

async function scanPage() {
  if (!state.activeProfile) {
    setStatusKey('status.loadProfileBeforeScanning');
    return;
  }

  state.debug.lastAction = 'scan-start';
  state.debug.lastError = '';
  state.debug.lastScanAt = new Date().toISOString();
  state.debug.matchResponse = null;
  setStatus('Scanning page...');
  state.matches = [];
  state.blocked = [];
  state.elements = [];
  state.page = null;
  state.scannedTabId = null;
  state.scannedTabUrl = '';
  state.scannedProfileId = '';
  state.scanStaleKey = '';
  state.scanStaleReason = '';
  renderPageInfo();
  renderMatches();
  try {
    const tab = await activeTab();
    if (!tab || tab.id === undefined) throw new Error('No active tab');

    const scrapeResults = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ['content/scraper.js']
    });
    const scraped = scrapeResults && scrapeResults[0] ? scrapeResults[0].result : {};

    const scan = await chrome.tabs.sendMessage(tab.id, { type: 'SCAN_FORM' });
    const elements = Array.isArray(scan && scan.elements) ? scan.elements : [];
    state.debug.lastAction = 'scan-elements-detected';
    const tabPage = pageFromTab(tab);
    const page = {
      url: scraped && scraped.url ? scraped.url : tabPage.url,
      title: scraped && scraped.title ? scraped.title : tabPage.title,
      company: scraped && scraped.company ? scraped.company : tabPage.company,
      position: scraped && scraped.position ? scraped.position : tabPage.position,
      confidence: scraped && scraped.confidence ? scraped.confidence : tabPage.confidence
    };
    const payload = {
      profile: state.activeProfile,
      profileId: state.activeProfile.id || '',
      page,
      elements
    };
    const response = state.offline ? matchLocally(state.activeProfile, elements) : await matchFields(settings(), payload);
    state.debug.matchResponse = response;

    state.page = page;
    state.elements = elements;
    state.matches = Array.isArray(response && response.matches) ? response.matches : [];
    state.blocked = Array.isArray(response && response.blocked) ? response.blocked : [];
    state.scannedTabId = tab.id;
    state.scannedTabUrl = page.url;
    state.scannedProfileId = activeProfileId();
    state.scanStaleKey = '';
    state.scanStaleReason = '';
    renderPageInfo();
    renderMatches();

    await recordSafely({
      eventType: 'scan',
      status: 'success',
      page,
      profileId: state.activeProfile.id || '',
      fieldKeys: state.matches.map(matchFieldKey).filter(Boolean),
      elementSummaries: elements.map(summarizeElement),
      errors: []
    });

    setStatus(state.offline ? 'Offline matches ready' : 'Matches ready');
    state.debug.lastAction = 'scan-complete';
    renderDebug();
  } catch (error) {
    state.debug.lastAction = 'scan-error';
    state.debug.lastError = error.message;
    state.matches = [];
    state.blocked = [];
    state.elements = [];
    state.page = null;
    state.scannedTabId = null;
    state.scannedTabUrl = '';
    state.scannedProfileId = '';
    state.scanStaleKey = '';
    state.scanStaleReason = '';
    renderPageInfo();
    renderMatches();
    setStatusKey('status.scanFailed', 'danger', { message: error.message });
  }
}

async function fillSelected() {
  if (state.scannedTabId === null) {
    if (state.scanStaleKey) setStatusKey(state.scanStaleKey);
    else setStatusKey('status.scanFirst');
    return;
  }

  const selected = Array.from(document.querySelectorAll('#matches input[type="checkbox"]:checked'));
  if (selected.length === 0) {
    setStatusKey('status.selectAtLeastOne');
    return;
  }

  const selectedRows = new Set(selected.map((input) => Number(input.value)));
  const selectedMatches = state.matches.filter((_match, index) => selectedRows.has(index));
  const items = selectedMatches.map((match) => ({
    elementIndex: matchElementIndex(match),
    value: match.field && match.field.value ? match.field.value : ''
  }));

  state.debug.lastAction = 'fill-start';
  state.debug.lastError = '';
  setStatus('Filling selected fields...');
  try {
    const tab = await chrome.tabs.get(state.scannedTabId);
    if (!tab || tab.id === undefined) throw new Error('Scanned tab is no longer available');
    if (state.scannedTabUrl && tab.url !== state.scannedTabUrl) throw new Error('Page changed, scan again before filling');

    const response = await chrome.tabs.sendMessage(tab.id, { type: 'FILL_SELECTED', items });
    const results = Array.isArray(response && response.results) ? response.results : [];
    const successCount = results.filter((result) => result && result.success).length;
    const errors = results.filter((result) => !result || !result.success).map((result) => safeText(result && result.error, 'Unknown fill error'));

    await recordSafely({
      eventType: 'fill',
      status: errors.length ? (successCount ? 'partial' : 'failed') : 'success',
      page: state.page || {},
      profileId: state.activeProfile ? state.activeProfile.id || '' : '',
      fieldKeys: selectedMatches.map(matchFieldKey).filter(Boolean),
      elementSummaries: selectedMatches.map((match) => summarizeElement(match.element || {})),
      errors
    });

    setStatus(errors.length ? `Filled ${successCount}, failed ${errors.length}` : `Filled ${successCount} field${successCount === 1 ? '' : 's'}`);
    state.debug.lastAction = errors.length ? 'fill-partial' : 'fill-complete';
    state.debug.lastError = errors.join('; ');
    updateFillButtonState();
  } catch (error) {
    state.debug.lastAction = 'fill-error';
    state.debug.lastError = error.message;
    await recordSafely({
      eventType: 'fill',
      status: 'failed',
      page: state.page || {},
      profileId: state.activeProfile ? state.activeProfile.id || '' : '',
      fieldKeys: selectedMatches.map(matchFieldKey).filter(Boolean),
      elementSummaries: selectedMatches.map((match) => summarizeElement(match.element || {})),
      errors: [error.message]
    });
    if (error.message && error.message.includes('Page changed')) {
      state.scanStaleKey = 'status.pageChanged';
      state.scanStaleReason = tr(state.scanStaleKey);
      state.scannedTabId = null;
      state.scannedTabUrl = '';
      state.scannedProfileId = '';
      setStatusKey(state.scanStaleKey);
    } else {
      setStatusKey('status.fillFailed', 'danger', { message: error.message });
    }
    updateFillButtonState();
  }
}

async function refreshProfiles(options = {}) {
  if (!state.token) {
    state.debug.lastAction = 'refresh-without-login';
    state.offline = false;
    state.profileSummaries = [];
    state.activeProfile = null;
    clearScanForProfileChange();
    await setActiveProfileId('');
    setStatusKey('auth.loginRequired');
    render();
    return;
  }

  setStatus('Connecting...');
  state.debug.lastAction = 'refresh-profiles';
  state.debug.lastError = '';
  if (options.invalidateExistingScan) {
    clearScanForProfileChange(options.reasonKey || 'status.profileRefreshed');
  }

  try {
    const summaries = await listProfiles(settings());
    state.offline = false;
    state.profileSummaries = Array.isArray(summaries) ? summaries : [];

    if (state.profileSummaries.length === 0) {
      state.activeProfile = null;
      clearScanForProfileChange();
      await cacheProfiles([]);
      await setActiveProfileId('');
      setStatusKey('status.noProfiles');
      render();
      return;
    }

    const savedProfileId = await getActiveProfileId();
    const selectedProfileId = state.profileSummaries.some((profile) => profile.id === savedProfileId)
      ? savedProfileId
      : state.profileSummaries[0].id;

    await loadProfile(selectedProfileId);
    await cacheProfiles(state.activeProfile ? [state.activeProfile] : []);
    restoreStatus('Connected');
  } catch (error) {
    if (error.status === 401) {
      state.debug.lastAction = 'refresh-unauthorized';
      state.debug.lastError = error.message;
      state.token = '';
      state.username = '';
      state.offline = false;
      state.profileSummaries = [];
      state.activeProfile = null;
      await clearAuthSession();
      await setActiveProfileId('');
      setStatusKey('auth.loginRequired', 'danger');
      render();
      return;
    }

    const cachedProfiles = await getCachedProfiles();
    state.debug.lastAction = 'refresh-offline-fallback';
    state.debug.lastError = error.message;
    const previousProfileId = activeProfileId();
    state.offline = true;
    state.profileSummaries = cachedProfiles.map(summarizeProfile).filter((profile) => profile.id);
    state.activeProfile = cachedProfiles[0] || null;
    if (previousProfileId && previousProfileId !== activeProfileId()) {
      clearScanForProfileChange();
    }
    if (state.activeProfile) restoreStatus('Offline');
    else setStatus('Disconnected');
    render();
  }
}

async function logIn() {
  const username = $('usernameInput').value.trim();
  const password = $('passwordInput').value;
  state.apiBase = $('apiBaseInput').value || DEFAULT_API_BASE;
  state.username = username;
  await saveSettings(settings());

  if (!username || !password) {
    setStatusKey('auth.credentialsRequired');
    return;
  }

  $('loginBtn').disabled = true;
  setStatusKey('auth.loggingIn', 'busy');
  try {
    const session = await loginAccount({ apiBase: state.apiBase }, { username, password });
    if (!session.accessToken) throw new Error('Missing access token');
    state.token = session.accessToken;
    state.username = session.username || username;
    await saveAuthSession({ token: state.token, username: state.username });
    $('passwordInput').value = '';
    render();
    await refreshProfiles({ invalidateExistingScan: true, reasonKey: 'auth.loggedIn' });
  } catch (error) {
    setStatusKey('auth.loginFailed', 'danger', { message: error.message });
    renderSettings();
  } finally {
    $('loginBtn').disabled = false;
  }
}

async function logOut() {
  state.token = '';
  state.username = '';
  state.profileSummaries = [];
  state.activeProfile = null;
  state.offline = false;
  state.matches = [];
  state.blocked = [];
  state.page = null;
  state.elements = [];
  state.scannedTabId = null;
  state.scannedTabUrl = '';
  state.scannedProfileId = '';
  state.scanStaleKey = '';
  state.scanStaleReason = '';
  await clearAuthSession();
  await setActiveProfileId('');
  render();
  setStatusKey('auth.signedOut');
}

function bind() {
  $('saveSettingsBtn').addEventListener('click', async () => {
    clearScanForProfileChange('settings.changed');
    state.apiBase = $('apiBaseInput').value || DEFAULT_API_BASE;
    await saveSettings(settings());
    render();
    if (state.token) await refreshProfiles({ invalidateExistingScan: true, reasonKey: 'settings.changed' });
    else setStatusKey('auth.loginRequired');
  });

  $('loginBtn').addEventListener('click', logIn);
  $('logoutBtn').addEventListener('click', logOut);
  $('refreshProfilesBtn').addEventListener('click', () => refreshProfiles({ invalidateExistingScan: true }));
  document.querySelectorAll('.lang-btn').forEach((button) => {
    button.addEventListener('click', () => changeLanguage(button.dataset.language));
  });
  $('profileSelect').addEventListener('change', async (event) => {
    try {
      const selectedProfileId = event.target.value;
      if (selectedProfileId && selectedProfileId !== activeProfileId()) {
        clearScanForProfileChange();
      }
      setStatusKey(state.offline ? 'status.loadingCachedProfile' : 'status.loadingProfile', 'busy');
      if (state.offline) {
        const cachedProfiles = await getCachedProfiles();
        const previousProfileId = activeProfileId();
        state.activeProfile = cachedProfiles.find((profile) => profile.id === selectedProfileId) || null;
        await setActiveProfileId(state.activeProfile ? state.activeProfile.id : '');
        if (previousProfileId && previousProfileId !== activeProfileId()) {
          clearScanForProfileChange();
        }
        render();
        if (state.activeProfile) restoreStatus('Offline');
        else setStatus('Disconnected');
        return;
      }

      await loadProfile(selectedProfileId);
      await cacheProfiles(state.activeProfile ? [state.activeProfile] : []);
      restoreStatus('Connected');
    } catch (error) {
      setStatusKey('status.profileLoadFailed', 'danger', { message: error.message });
    }
  });
  $('scanBtn').addEventListener('click', scanPage);
  $('fillBtn').addEventListener('click', fillSelected);
  if (chrome.tabs && chrome.tabs.onUpdated) {
    chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
      if (state.scannedTabId !== null && tabId === state.scannedTabId && changeInfo.url && changeInfo.url !== state.scannedTabUrl) {
        markScanStale('status.pageChanged');
      }
    });
  }
  if (chrome.tabs && chrome.tabs.onActivated) {
    chrome.tabs.onActivated.addListener(({ tabId }) => {
      if (state.scannedTabId !== null && tabId !== state.scannedTabId) {
        markScanStale('status.activeTabChanged');
      }
    });
  }
}

async function init() {
  const storedSettings = await getSettings();
  state.language = await getLanguage();
  state.apiBase = storedSettings.apiBase;
  state.token = storedSettings.token;
  state.username = storedSettings.username;
  bind();
  render();
  await refreshProfiles();
}

init();
