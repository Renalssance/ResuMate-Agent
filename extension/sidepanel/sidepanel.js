import { DEFAULT_API_BASE } from '../lib/constants.js';

const state = {
  apiBase: DEFAULT_API_BASE,
  token: '',
  profiles: [],
  activeProfile: null,
  matches: []
};

const $ = (id) => document.getElementById(id);

function setStatus(text) {
  $('statusText').textContent = text;
}

function renderProfiles() {
  const profileSelect = $('profileSelect');
  const options = state.profiles.map((profile) => {
    const option = document.createElement('option');
    option.value = profile.id;
    option.textContent = profile.name;
    return option;
  });

  profileSelect.replaceChildren(...options);
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
  label.textContent = field.label;

  const value = document.createElement('div');
  value.className = 'muted';
  value.textContent = field.value;

  container.append(label, value);
  return container;
}

function renderProfileFields() {
  const profileFields = $('profileFields');
  const fields = state.activeProfile
    ? state.activeProfile.sections.flatMap((section) => section.fields).filter((field) => field.value).slice(0, 8)
        .map(createProfileField)
    : createFallbackProfileFields();

  profileFields.replaceChildren(...fields);
}

function render() {
  $('apiBaseInput').value = state.apiBase;
  $('tokenInput').value = state.token;
  renderProfiles();
  renderProfileFields();
}

function bind() {
  $('saveSettingsBtn').addEventListener('click', () => {
    state.apiBase = $('apiBaseInput').value || DEFAULT_API_BASE;
    state.token = $('tokenInput').value || '';
    setStatus('Settings saved');
    render();
  });
  $('refreshProfilesBtn').addEventListener('click', () => setStatus('Profile loading is added in the next task'));
  $('scanBtn').addEventListener('click', () => setStatus('Scanning is added in the fill-engine task'));
}

bind();
render();
