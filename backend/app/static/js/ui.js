// Small DOM helpers. All dynamic text is inserted with textContent (never
// innerHTML) so data from the API cannot inject markup.

export function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  // Let callers chain .append(...) with optional (null/false) items safely.
  const append = node.append.bind(node);
  node.append = (...items) => append(...items.flat().filter((x) => x !== null && x !== undefined && x !== false));
  return node;
}

export function $(selector, root = document) {
  return root.querySelector(selector);
}

export function alertBox(type, message, { requestId, title } = {}) {
  return h('div', { class: `alert alert-${type}`, role: type === 'danger' || type === 'warning' ? 'alert' : 'status' },
    title ? h('strong', { class: 'd-block' }, title) : null,
    message,
    requestId ? h('div', { class: 'small text-muted mt-1' }, `Reference: ${requestId}`) : null);
}

export function showAlert(container, type, message, opts = {}) {
  const target = typeof container === 'string' ? $(container) : container;
  if (!target) return;
  clear(target).append(alertBox(type, message, opts));
  if (type === 'danger' || type === 'warning') target.scrollIntoView({ block: 'nearest' });
}

export function showError(container, err) {
  showAlert(container, 'danger', err.message || 'Something went wrong.', { requestId: err.requestId });
}

export function loading(container, text = 'Loading…') {
  const target = typeof container === 'string' ? $(container) : container;
  clear(target).append(
    h('div', { class: 'd-flex align-items-center gap-2 text-muted py-3', role: 'status' },
      h('div', { class: 'spinner-border spinner-border-sm', 'aria-hidden': 'true' }), text));
}

export function empty(container, text) {
  const target = typeof container === 'string' ? $(container) : container;
  clear(target).append(h('p', { class: 'text-muted fst-italic py-2' }, text));
}

// Field-level validation messages from {details:[{field,message}]}
export function applyFieldErrors(form, details = []) {
  form.querySelectorAll('.is-invalid').forEach((el) => el.classList.remove('is-invalid'));
  form.querySelectorAll('.invalid-feedback[data-dynamic]').forEach((el) => el.remove());
  let first = null;
  const unmatched = [];
  for (const { field, message } of details) {
    const input = form.querySelector(`[name="${CSS.escape(field)}"]`);
    if (!input) { unmatched.push(message); continue; }
    input.classList.add('is-invalid');
    input.setAttribute('aria-invalid', 'true');
    const fb = h('div', { class: 'invalid-feedback', id: `${field}-error`, 'data-dynamic': '1' }, message);
    input.setAttribute('aria-describedby', `${field}-error`);
    (input.closest('.form-check') || input.parentElement).append(fb);
    first = first || input;
  }
  if (first) first.focus();
  return unmatched;
}

export function clearFieldErrors(form) {
  applyFieldErrors(form, []);
  form.querySelectorAll('[aria-invalid]').forEach((el) => el.removeAttribute('aria-invalid'));
}

const DATE_FMT = new Intl.DateTimeFormat('en-NG', {
  timeZone: 'Africa/Lagos', dateStyle: 'medium', timeStyle: 'short',
});

export function fmtDate(iso) {
  if (!iso) return '—';
  return `${DATE_FMT.format(new Date(iso))} WAT`;
}

// <input type="datetime-local"> values are interpreted as West Africa Time (UTC+1).
export function localInputToIso(value) {
  if (!value) return null;
  return `${value}:00+01:00`;
}

export function isoToLocalInput(iso) {
  if (!iso) return '';
  const d = new Date(new Date(iso).getTime() + 60 * 60 * 1000);
  return d.toISOString().slice(0, 16);
}

// Monochrome status labels (design.md: single accent, no extra colours).
const STATUS_STYLE = {
  verified: 'strong', open: 'strong', voting_open: 'strong', active: 'strong',
  pending: 'outline', scheduled: 'outline', opening_soon: 'outline', draft: 'outline',
  closed: '', voting_ended: '', archived: 'off', rejected: 'off', suspended: 'off', cancelled: 'off', inactive: 'off',
};
const STATUS_TEXT = {
  voting_open: 'Open', opening_soon: 'Opens soon', voting_ended: 'Ended', open: 'Open',
};

export function badge(status, label) {
  const text = label || STATUS_TEXT[status] || (status || '').replace(/_/g, ' ');
  const style = STATUS_STYLE[status];
  return h('span', { class: `status${style ? ` status-${style}` : ''}` }, text);
}

export function setBusy(button, busy, busyText = 'Please wait…') {
  if (!button) return;
  if (busy) {
    button.dataset.label = button.textContent;
    button.textContent = busyText;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
  } else {
    if (button.dataset.label) button.textContent = button.dataset.label;
    button.disabled = false;
    button.removeAttribute('aria-busy');
  }
}

export function formJson(form) {
  const data = {};
  for (const [key, value] of new FormData(form).entries()) data[key] = typeof value === 'string' ? value.trim() : value;
  return data;
}

export function initials(name) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('');
}
