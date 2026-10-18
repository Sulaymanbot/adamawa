// Thin fetch() wrapper for the /api/v1 JSON API.
// Same-origin only; the session cookie is sent automatically and the CSRF
// token from <meta name="csrf-token"> is attached to state-changing requests.

export class ApiError extends Error {
  constructor(status, code, message, details = [], requestId = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

export function setCsrfToken(token) {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && token) meta.setAttribute('content', token);
}

async function request(method, path, body, extraHeaders = {}) {
  const headers = { Accept: 'application/json', ...extraHeaders };
  const init = { method, headers, credentials: 'same-origin' };
  if (method !== 'GET') {
    headers['X-CSRFToken'] = csrfToken();
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
  }
  let response;
  try {
    response = await fetch(`/api/v1${path}`, init);
  } catch {
    throw new ApiError(0, 'network_error', 'Could not reach the server. Check your connection and try again.');
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError(response.status, 'bad_response', 'The server sent an unexpected response.');
  }
  if (!response.ok || !payload.ok) {
    const err = payload && payload.error ? payload.error : {};
    const apiErr = new ApiError(response.status, err.code || 'error', err.message || 'Request failed.', err.details || [], payload && payload.request_id);
    if (response.status === 401 && ['session_expired', 'unauthenticated'].includes(apiErr.code) && document.body.dataset.role) {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
    throw apiErr;
  }
  return { data: payload.data, meta: payload.meta || {}, requestId: payload.request_id };
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body, headers) => request('POST', path, body, headers),
  patch: (path, body) => request('PATCH', path, body),
  del: (path) => request('DELETE', path),
};
