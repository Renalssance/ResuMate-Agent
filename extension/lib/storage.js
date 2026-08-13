import { DEFAULT_API_BASE, STORAGE_KEYS } from './constants.js';
import { defaultLanguage, normalizeLanguage } from './i18n.js';

export async function getSettings() {
  const data = await chrome.storage.local.get([STORAGE_KEYS.apiBase, STORAGE_KEYS.authToken, STORAGE_KEYS.username]);
  return {
    apiBase: data[STORAGE_KEYS.apiBase] || DEFAULT_API_BASE,
    token: data[STORAGE_KEYS.authToken] || '',
    username: data[STORAGE_KEYS.username] || ''
  };
}

export async function saveSettings(settings) {
  await chrome.storage.local.set({
    [STORAGE_KEYS.apiBase]: settings.apiBase || DEFAULT_API_BASE,
  });
}

export async function saveAuthSession(session) {
  await chrome.storage.local.set({
    [STORAGE_KEYS.authToken]: session.token || '',
    [STORAGE_KEYS.username]: session.username || ''
  });
}

export async function clearAuthSession() {
  await chrome.storage.local.remove([STORAGE_KEYS.authToken, STORAGE_KEYS.username]);
}

export async function getCachedProfiles() {
  const data = await chrome.storage.local.get(STORAGE_KEYS.profiles);
  return Array.isArray(data[STORAGE_KEYS.profiles]) ? data[STORAGE_KEYS.profiles] : [];
}

export async function cacheProfiles(profiles) {
  await chrome.storage.local.set({ [STORAGE_KEYS.profiles]: profiles || [] });
}

export async function getActiveProfileId() {
  const data = await chrome.storage.local.get(STORAGE_KEYS.activeProfileId);
  return data[STORAGE_KEYS.activeProfileId] || '';
}

export async function setActiveProfileId(profileId) {
  await chrome.storage.local.set({ [STORAGE_KEYS.activeProfileId]: profileId || '' });
}

export async function getLanguage() {
  const data = await chrome.storage.local.get(STORAGE_KEYS.language);
  if (data[STORAGE_KEYS.language]) return normalizeLanguage(data[STORAGE_KEYS.language]);
  const browserLanguage = chrome.i18n && chrome.i18n.getUILanguage ? chrome.i18n.getUILanguage() : '';
  return defaultLanguage(browserLanguage);
}

export async function setLanguage(language) {
  await chrome.storage.local.set({ [STORAGE_KEYS.language]: normalizeLanguage(language) });
}
