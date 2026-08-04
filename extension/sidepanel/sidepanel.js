import { DEFAULT_API_BASE } from '../lib/constants.js';
import { getProfile, listProfiles } from '../lib/api-client.js';
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
  matches: []
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

function render() {
  renderSettings();
  renderProfiles();
  renderFields();
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
  $('scanBtn').addEventListener('click', () => setStatus('Scanning is added in the fill-engine task'));
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
