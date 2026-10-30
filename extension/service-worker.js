import { captureJob, getProfile, listProfiles, login, matchFields, recordEvent } from './lib/api-client.js';
import { cacheProfiles, clearAuthSession, getCachedProfiles, getSettings, saveAuthSession, saveSettings } from './lib/storage.js';

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
const storageReady = chrome.storage.local.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' });
const isObject = value => Boolean(value && typeof value === 'object' && !Array.isArray(value));
const isText = value => typeof value === 'string';
const nonempty = value => isText(value) && Boolean(value.trim());

function requirePayload(condition) {
  if (!condition) throw new Error('Invalid message payload');
}

async function session() {
  const settings = await getSettings();
  return { apiBase: settings.apiBase, authenticated: Boolean(settings.token), username: settings.username };
}

async function sameSession(settings) {
  const current = await getSettings();
  return settings.token === current.token && settings.apiBase === current.apiBase;
}

async function handleMessage(request, settings) {
  requirePayload(isObject(request) && isText(request.type));
  const payload = request.payload;
  switch (request.type) {
    case 'GET_SESSION':
      return session();
    case 'SAVE_SETTINGS': {
      requirePayload(isObject(payload) && nonempty(payload.apiBase));
      const apiBase = payload.apiBase.trim().replace(/\/+$/, '');
      const url = new URL(apiBase);
      requirePayload(['http:', 'https:'].includes(url.protocol));
      if (apiBase !== settings.apiBase) await clearAuthSession();
      await saveSettings({ apiBase });
      return session();
    }
    case 'AUTH_LOGIN': {
      requirePayload(isObject(payload) && nonempty(payload.username) && nonempty(payload.password));
      await clearAuthSession();
      const loggedIn = await login(settings, payload);
      if (!loggedIn.accessToken) throw new Error('Missing access token');
      await saveAuthSession({ token: loggedIn.accessToken, username: loggedIn.username || payload.username.trim() });
      return session();
    }
    case 'AUTH_LOGOUT':
      await clearAuthSession();
      return session();
    case 'LIST_PROFILES':
      return listProfiles(settings);
    case 'GET_PROFILE': {
      requirePayload(isObject(payload) && nonempty(payload.profileId));
      const profile = await getProfile(settings, payload.profileId);
      if (!await sameSession(settings)) throw new Error('Account changed while loading profile');
      const cached = await getCachedProfiles();
      await cacheProfiles([...cached.filter(item => item.id !== profile.id), profile]);
      return profile;
    }
    case 'MATCH_FIELDS':
      requirePayload(isObject(payload) && nonempty(payload.profileId) && isObject(payload.page) && Array.isArray(payload.elements) && payload.elements.every(element => isObject(element) && Number.isInteger(element.index) && element.index >= 0 && isText(element.tag)));
      return matchFields(settings, { profileId: payload.profileId, page: payload.page, elements: payload.elements });
    case 'CAPTURE_JOB_PAGE': {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id) throw new Error('No active page');
      const [metadata] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content/scraper.js'] });
      const [captured] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content/job-capture.js'] });
      if (!captured?.result?.text?.trim()) throw new Error('No readable job description');
      return { title: captured.result.title || metadata?.result?.position || '', company: metadata?.result?.company || '', text: captured.result.text, sourceUrl: captured.result.sourceUrl };
    }
    case 'SAVE_JOB':
      requirePayload(isObject(payload) && nonempty(payload.title) && payload.title.length <= 255 && nonempty(payload.text) && (payload.company === undefined || (isText(payload.company) && payload.company.length <= 255)) && (payload.sourceUrl == null || (isText(payload.sourceUrl) && payload.sourceUrl.length <= 1024)) && (payload.primaryResumeId == null || (Number.isInteger(payload.primaryResumeId) && payload.primaryResumeId > 0)) && (payload.sourceSite == null || isText(payload.sourceSite)) && (payload.sourceJobId == null || isText(payload.sourceJobId)) && Boolean(payload.sourceSite) === Boolean(payload.sourceJobId));
      return captureJob(settings, payload);
    case 'RECORD_EVENT':
      requirePayload(isObject(payload) && ['scan', 'match', 'fill'].includes(payload.eventType) && ['success', 'partial', 'failed'].includes(payload.status) && isObject(payload.page) && isText(payload.profileId) && Array.isArray(payload.fieldKeys) && payload.fieldKeys.every(isText) && Array.isArray(payload.elementSummaries) && payload.elementSummaries.every(isObject) && Array.isArray(payload.errors) && payload.errors.every(isText));
      return recordEvent(settings, payload);
    default:
      throw new Error('Unknown message type');
  }
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  (async () => {
    let owner;
    try {
      if (sender?.id !== chrome.runtime.id || sender?.url !== chrome.runtime.getURL('sidepanel/sidepanel.html')) throw new Error('Untrusted message sender');
      await storageReady;
      owner = await getSettings();
      const data = await handleMessage(request, owner);
      if (['LIST_PROFILES', 'GET_PROFILE', 'MATCH_FIELDS', 'RECORD_EVENT', 'SAVE_JOB'].includes(request.type) && !await sameSession(owner)) throw new Error('Account changed while waiting for response');
      sendResponse({ ok: true, data });
    } catch (error) {
      if (error.status === 401 && owner && await sameSession(owner)) await clearAuthSession();
      sendResponse({ ok: false, error: { message: error.message, ...(error.status ? { status: error.status } : {}) } });
    }
  })();
  return true;
});
