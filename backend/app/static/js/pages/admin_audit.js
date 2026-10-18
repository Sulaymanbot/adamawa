import { api } from '../api.js';
import { $, clear, empty, fmtDate, h, loading, showError } from '../ui.js';

const filters = $('#audit-filters');
const table = $('#audit-table');
let page = 1;

function pager(meta) {
  const nav = clear($('#audit-pager'));
  if (meta.pages <= 1) return;
  const mk = (label, target, disabled) => h('li', { class: `page-item${disabled ? ' disabled' : ''}` },
    h('button', { type: 'button', class: 'page-link', disabled, onclick: () => { page = target; load(); } }, label));
  nav.append(h('ul', { class: 'pagination' },
    mk('Newer', page - 1, page <= 1),
    h('li', { class: 'page-item disabled' }, h('span', { class: 'page-link' }, `Page ${meta.page} of ${meta.pages} (${meta.total} events)`)),
    mk('Older', page + 1, page >= meta.pages)));
}

async function load() {
  loading(table);
  const params = new URLSearchParams();
  for (const [k, v] of new FormData(filters).entries()) {
    if (!v) continue;
    if (k === 'from') params.set(k, `${v}T00:00:00+01:00`);
    else if (k === 'to') params.set(k, `${v}T23:59:59+01:00`);
    else params.set(k, v);
  }
  params.set('page', page);
  try {
    const { data, meta } = await api.get(`/admin/audit-logs?${params}`);
    if (!data.length) { empty(table, 'No events found.'); clear($('#audit-pager')); return; }
    clear(table).append(h('div', { class: 'table-responsive' }, h('table', { class: 'table table-sm align-middle mb-0' },
      h('caption', { class: 'visually-hidden' }, 'Audit events, newest first'),
      h('thead', {}, h('tr', {}, ['Time', 'Event', 'By', 'On', 'Details', 'Ref'].map((t) => h('th', { scope: 'col' }, t)))),
      h('tbody', {}, data.map((e) => h('tr', {},
        h('td', { class: 'small text-nowrap' }, fmtDate(e.created_at)),
        h('td', {}, h('code', {}, e.event_type)),
        h('td', { class: 'small' }, e.actor_user_id ? `#${e.actor_user_id} (${e.actor_role})` : 'anonymous'),
        h('td', { class: 'small' }, e.entity_type ? `${e.entity_type} #${e.entity_id}` : '—'),
        h('td', { class: 'small' }, e.description),
        h('td', { class: 'small' }, h('code', {}, (e.request_id || '').slice(0, 8)))))))));
    pager(meta);
  } catch (err) {
    clear(table);
    showError('#audit-alert', err);
  }
}

filters.addEventListener('submit', (event) => { event.preventDefault(); page = 1; load(); });
load();
