import { DEFAULT_API_BASE, STORAGE_KEYS } from './constants.js';

export async function getSettings() {
  const data = await chrome.storage.local.get([STORAGE_KEYS.apiBase, STORAGE_KEYS.authToken]);
  return {
    apiBase: data[STORAGE_KEYS.apiBase] || DEFAULT_API_BASE,
    token: data[STORAGE_KEYS.authToken] || ''
  };
}

export async function saveSettings(settings) {
  await chrome.storage.local.set({
    [STORAGE_KEYS.apiBase]: settings.apiBase || DEFAULT_API_BASE,
    [STORAGE_KEYS.authToken]: settings.token || ''
  });
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
