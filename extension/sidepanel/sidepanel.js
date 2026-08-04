import { DEFAULT_API_BASE } from '../lib/constants.js';
import { getProfile, listProfiles, matchFields, recordEvent } from '../lib/api-client.js';
import { matchLocally } from '../lib/field-matcher.js';
import {
  cacheProfiles,
  getActiveProfileId,
  getCachedProfiles,
  getSettings,
  saveSettings,
  setActiveProfileId
} from '../lib/storage.js';

const state = {
  apiBase: DEFAULT_API_BASE,
  token: '',
  profileSummaries: [],
  activeProfile: null,
  offline: false,
  matches: [],
  page: null,
  elements: []
};

const $ = (id) => document.getElementById(id);

function settings() {
  return {
    apiBase: state.apiBase,
    token: state.token
  };
}

function setStatus(text) {
  $('statusText').textContent = text;
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

function renderSettings() {
  $('apiBaseInput').value = state.apiBase;
  $('tokenInput').value = state.token;
}

function renderProfiles() {
  const profileSelect = $('profileSelect');
  const options = state.profileSummaries.map((profile) => {
    const option = document.createElement('option');
    option.value = profile.id;
    option.textContent = profile.name || profile.id;
    return option;
  });

  profileSelect.replaceChildren(...options);
  profileSelect.value = state.activeProfile ? state.activeProfile.id : '';
}

function createFallbackProfileFields() {
  const fallback = document.createElement('div');
  fallback.className = 'muted';
  fallback.textContent = 'No profile loaded';
  return [fallback];
}

function createProfileField(field) {
  const container = document.createElement('div');
  container.className = 'field';

  const label = document.createElement('strong');
  label.textContent = field.label || field.key || 'Field';

  const value = document.createElement('div');
  value.className = 'muted';
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

function createEmptyMatches(text) {
  const empty = document.createElement('div');
  empty.className = 'muted';
  empty.textContent = text;
  return [empty];
}

function createMatchRow(match) {
  const row = document.createElement('label');
  row.className = 'match';

  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.checked = true;
  checkbox.value = String(matchElementIndex(match));

  const details = document.createElement('div');

  const title = document.createElement('strong');
  const fieldLabel = match.field ? safeText(match.field.label || match.field.key, 'Field') : 'Field';
  const element = match.element || {};
  const elementLabel = element.labelText || element.placeholder || element.name || element.id || `Element ${matchElementIndex(match)}`;
  title.textContent = `${fieldLabel} -> ${elementLabel}`;

  const value = document.createElement('div');
  value.className = 'muted';
  value.textContent = match.field ? safeText(match.field.value) : '';

  const reason = document.createElement('div');
  reason.className = 'muted';
  reason.textContent = safeText(match.reason || match.confidence);

  details.append(title, value, reason);
  row.append(checkbox, details);
  return row;
}

function renderMatches() {
  const matchesContainer = $('matches');
  const matches = Array.isArray(state.matches) ? state.matches : [];
  $('fillBtn').disabled = matches.length === 0;
  matchesContainer.replaceChildren(...(matches.length ? matches.map(createMatchRow) : createEmptyMatches('No matches yet')));
}

function render() {
  renderSettings();
  renderProfiles();
  renderFields();
  renderMatches();
}

async function activeTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0] || null;
}

async function loadProfile(profileId) {
  if (!profileId) {
    state.activeProfile = null;
    await setActiveProfileId('');
    render();
    return;
  }

  const profile = await getProfile(settings(), profileId);
  state.activeProfile = profile;
  await setActiveProfileId(profile.id || profileId);
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
    setStatus('Load a profile before scanning');
    return;
  }

  setStatus('Scanning page...');
  try {
    const tab = await activeTab();
    if (!tab || tab.id === undefined) throw new Error('No active tab');

    const scan = await chrome.tabs.sendMessage(tab.id, { type: 'SCAN_FORM' });
    const elements = Array.isArray(scan && scan.elements) ? scan.elements : [];
    const page = pageFromTab(tab);
    const payload = {
      profile: state.activeProfile,
      profileId: state.activeProfile.id || '',
      page,
      elements
    };
    const response = state.offline ? matchLocally(state.activeProfile, elements) : await matchFields(settings(), payload);

    state.page = page;
    state.elements = elements;
    state.matches = Array.isArray(response && response.matches) ? response.matches : [];
    $('pageInfo').textContent = `${safeText(page.title || page.url, 'Current page')} - ${elements.length} fields, ${state.matches.length} matches`;
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
  } catch (error) {
    state.matches = [];
    renderMatches();
    setStatus(`Scan failed: ${error.message}`);
  }
}

async function fillSelected() {
  const selected = Array.from(document.querySelectorAll('#matches input[type="checkbox"]:checked'));
  if (selected.length === 0) {
    setStatus('Select at least one match');
    return;
  }

  const selectedIndexes = new Set(selected.map((input) => Number(input.value)));
  const selectedMatches = state.matches.filter((match) => selectedIndexes.has(matchElementIndex(match)));
  const items = selectedMatches.map((match) => ({
    elementIndex: matchElementIndex(match),
    value: match.field && match.field.value ? match.field.value : ''
  }));

  setStatus('Filling selected fields...');
  try {
    const tab = await activeTab();
    if (!tab || tab.id === undefined) throw new Error('No active tab');

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

    setStatus(`Filled ${successCount}, failed ${errors.length}`);
  } catch (error) {
    await recordSafely({
      eventType: 'fill',
      status: 'failed',
      page: state.page || {},
      profileId: state.activeProfile ? state.activeProfile.id || '' : '',
      fieldKeys: selectedMatches.map(matchFieldKey).filter(Boolean),
      elementSummaries: selectedMatches.map((match) => summarizeElement(match.element || {})),
      errors: [error.message]
    });
    setStatus(`Fill failed: ${error.message}`);
  }
}

async function refreshProfiles() {
  setStatus('Connecting...');

  try {
    const summaries = await listProfiles(settings());
    state.offline = false;
    state.profileSummaries = Array.isArray(summaries) ? summaries : [];

    if (state.profileSummaries.length === 0) {
      state.activeProfile = null;
      await cacheProfiles([]);
      await setActiveProfileId('');
      setStatus('No profiles');
      render();
      return;
    }

    const savedProfileId = await getActiveProfileId();
    const selectedProfileId = state.profileSummaries.some((profile) => profile.id === savedProfileId)
      ? savedProfileId
      : state.profileSummaries[0].id;

    await loadProfile(selectedProfileId);
    await cacheProfiles(state.activeProfile ? [state.activeProfile] : []);
    setStatus('Connected');
  } catch (error) {
    const cachedProfiles = await getCachedProfiles();
    state.offline = true;
    state.profileSummaries = cachedProfiles.map(summarizeProfile).filter((profile) => profile.id);
    state.activeProfile = cachedProfiles[0] || null;
    setStatus(state.activeProfile ? 'Offline' : 'Disconnected');
    render();
  }
}

function bind() {
  $('saveSettingsBtn').addEventListener('click', async () => {
    state.apiBase = $('apiBaseInput').value || DEFAULT_API_BASE;
    state.token = $('tokenInput').value || '';
    await saveSettings(settings());
    render();
    await refreshProfiles();
  });

  $('refreshProfilesBtn').addEventListener('click', refreshProfiles);
  $('profileSelect').addEventListener('change', async (event) => {
    try {
      setStatus(state.offline ? 'Loading cached profile...' : 'Loading profile...');
      if (state.offline) {
        const cachedProfiles = await getCachedProfiles();
        state.activeProfile = cachedProfiles.find((profile) => profile.id === event.target.value) || null;
        await setActiveProfileId(state.activeProfile ? state.activeProfile.id : '');
        render();
        setStatus(state.activeProfile ? 'Offline' : 'Disconnected');
        return;
      }

      await loadProfile(event.target.value);
      await cacheProfiles(state.activeProfile ? [state.activeProfile] : []);
      setStatus('Connected');
    } catch (error) {
      setStatus(`Profile load failed: ${error.message}`);
    }
  });
  $('scanBtn').addEventListener('click', scanPage);
  $('fillBtn').addEventListener('click', fillSelected);
}

async function init() {
  const storedSettings = await getSettings();
  state.apiBase = storedSettings.apiBase;
  state.token = storedSettings.token;
  bind();
  render();
  await refreshProfiles();
}

init();
