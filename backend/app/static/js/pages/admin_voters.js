import { api } from '../api.js';
import { $, applyFieldErrors, badge, clear, clearFieldErrors, empty, fmtDate, h, loading, setBusy, showAlert, showError } from '../ui.js';

const filters = $('#voter-filters');
const table = $('#voters-table');
const modalEl = $('#verify-modal');
const modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
const verifyForm = $('#verify-form');
let page = 1;

const ACTIONS = {
  pending: [['verify', 'Verify', 'btn-outline-dark'], ['reject', 'Reject', 'btn-quiet']],
  verified: [['suspend', 'Suspend', 'btn-quiet']],
  rejected: [['verify', 'Verify', 'btn-outline-dark']],
  suspended: [['reactivate', 'Reactivate', 'btn-outline-dark']],
};

async function loadLgas() {
  const { data } = await api.get('/locations/lgas');
  for (const lga of data) filters.lga_id.append(h('option', { value: lga.id }, lga.name));
}

filters.lga_id.addEventListener('change', async () => {
  const ward = filters.ward_id;
  clear(ward).append(h('option', { value: '' }, 'Any'));
  ward.disabled = !filters.lga_id.value;
  if (!filters.lga_id.value) return;
  const { data } = await api.get(`/locations/lgas/${filters.lga_id.value}/wards`);
  for (const w of data) ward.append(h('option', { value: w.id }, w.name));
});

function openVerify(voter, action, label) {
  verifyForm.reset();
  clearFieldErrors(verifyForm);
  clear($('#verify-alert'));
  $('#verify-title').textContent = `${label} voter`;
  $('#verify-desc').textContent = `${voter.full_name} · ${voter.voter_id_masked}`;
  $('#verify-action').value = action;
  $('#reason-req').textContent = ['reject', 'suspend'].includes(action) ? '(required)' : '(optional)';
  verifyForm.dataset.voterId = voter.id;
  modal.show();
}

verifyForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const action = $('#verify-action').value;
  const reason = $('#verify-reason').value.trim();
  if (['reject', 'suspend'].includes(action) && !reason) {
    applyFieldErrors(verifyForm, [{ field: 'reason', message: 'Add a reason.' }]);
    return;
  }
  const button = $('#verify-submit');
  setBusy(button, true);
  try {
    await api.patch(`/admin/voters/${verifyForm.dataset.voterId}/verification`, { action, reason: reason || null });
    modal.hide();
    showAlert('#voters-alert', 'success', 'Status updated.');
    load();
  } catch (err) {
    showError('#verify-alert', err);
  } finally {
    setBusy(button, false);
  }
});

function pager(meta) {
  const nav = clear($('#voters-pager'));
  if (meta.pages <= 1) return;
  const mk = (label, target, disabled) => h('li', { class: `page-item${disabled ? ' disabled' : ''}` },
    h('button', { type: 'button', class: 'page-link', disabled, onclick: () => { page = target; load(); } }, label));
  nav.append(h('ul', { class: 'pagination' },
    mk('Previous', page - 1, page <= 1),
    h('li', { class: 'page-item disabled' }, h('span', { class: 'page-link' }, `Page ${meta.page} of ${meta.pages} (${meta.total})`)),
    mk('Next', page + 1, page >= meta.pages)));
}

async function load() {
  loading(table);
  // Search terms go in a POST body, never the URL, so personal data stays out of logs.
  const body = { page };
  for (const [k, v] of new FormData(filters).entries()) {
    if (!v) continue;
    body[k] = ['lga_id', 'ward_id'].includes(k) ? Number(v) : v;
  }
  try {
    const { data, meta } = await api.post('/admin/voters/search', body);
    if (!data.length) { empty(table, 'No voters found.'); clear($('#voters-pager')); return; }
    clear(table).append(h('div', { class: 'table-responsive' }, h('table', { class: 'table align-middle mb-0' },
      h('caption', { class: 'visually-hidden' }, 'Voters'),
      h('thead', {}, h('tr', {}, ['Name', 'Voter ID', 'Contact', 'Location', 'Status', 'Joined', ''].map((t) => h('th', { scope: 'col' }, t)))),
      h('tbody', {}, data.map((v) => h('tr', {},
        h('th', { scope: 'row' }, v.full_name),
        h('td', {}, v.voter_id_masked),
        h('td', { class: 'small' }, v.email_masked, h('br'), v.phone_masked || ''),
        h('td', { class: 'small' }, `${v.lga.name} / ${v.ward.name}`),
        h('td', {}, badge(v.verification_status), v.verification_reason ? h('div', { class: 'small text-muted' }, v.verification_reason) : null),
        h('td', { class: 'small' }, fmtDate(v.registered_at)),
        h('td', {}, h('div', { class: 'd-flex flex-wrap gap-1' }, (ACTIONS[v.verification_status] || []).map(([action, label, cls]) =>
          h('button', { type: 'button', class: `btn btn-sm ${cls}`, 'aria-label': `${label} ${v.full_name}`, onclick: () => openVerify(v, action, label) }, label))))))))));
    pager(meta);
  } catch (err) {
    clear(table);
    showError('#voters-alert', err);
  }
}

filters.addEventListener('submit', (event) => { event.preventDefault(); page = 1; load(); });

const initial = new URLSearchParams(window.location.search).get('status');
if (initial) filters.status.value = initial;
loadLgas().catch((err) => showError('#voters-alert', err));
load();
