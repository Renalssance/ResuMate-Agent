function headers(token) {
  const value = { 'Content-Type': 'application/json' };
  if (token) value.Authorization = `Bearer ${token}`;
  return value;
}

async function parseJsonResponse(response) {
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message = data && data.detail ? data.detail : `HTTP ${response.status}`;
    throw new Error(Array.isArray(message) ? JSON.stringify(message) : String(message));
  }
  return data;
}

export async function listProfiles(settings) {
  const response = await fetch(`${settings.apiBase}/api/autofill/profiles`, {
    headers: headers(settings.token)
  });
  return parseJsonResponse(response);
}

export async function getProfile(settings, profileId) {
  const response = await fetch(`${settings.apiBase}/api/autofill/profiles/${encodeURIComponent(profileId)}`, {
    headers: headers(settings.token)
  });
  return parseJsonResponse(response);
}

export async function matchFields(settings, payload) {
  const response = await fetch(`${settings.apiBase}/api/autofill/match`, {
    method: 'POST',
    headers: headers(settings.token),
    body: JSON.stringify(payload)
  });
  return parseJsonResponse(response);
}

export async function recordEvent(settings, payload) {
  const response = await fetch(`${settings.apiBase}/api/autofill/events`, {
    method: 'POST',
    headers: headers(settings.token),
    body: JSON.stringify(payload)
  });
  return parseJsonResponse(response);
}
