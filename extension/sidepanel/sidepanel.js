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

function render() {
  $('apiBaseInput').value = state.apiBase;
  $('tokenInput').value = state.token;
  $('profileSelect').innerHTML = state.profiles
    .map((profile) => `<option value="${profile.id}">${profile.name}</option>`)
    .join('');
  $('profileFields').innerHTML = state.activeProfile
    ? state.activeProfile.sections.flatMap((section) => section.fields).filter((field) => field.value).slice(0, 8)
        .map((field) => `<div class="field"><strong>${field.label}</strong><div class="muted">${field.value}</div></div>`)
        .join('')
    : '<div class="muted">No profile loaded</div>';
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
