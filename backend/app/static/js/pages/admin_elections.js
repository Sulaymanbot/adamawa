import { api } from '../api.js';
import { $, applyFieldErrors, badge, clear, clearFieldErrors, empty, fmtDate, h, loading, setBusy, showAlert, showError } from '../ui.js';
import { readElectionForm, setupElectionForm } from './election_form.js';

const form = $('#election-form');
const table = $('#elections-table');

async function load() {
  loading(table);
  try {
    const { data } = await api.get('/admin/elections');
    if (!data.length) { empty(table, 'No elections yet.'); return; }
    clear(table).append(h('div', { class: 'table-responsive' }, h('table', { class: 'table align-middle mb-0' },
      h('caption', { class: 'visually-hidden' }, 'Elections'),
      h('thead', {}, h('tr', {}, ['Title', 'Where', 'Voting (WAT)', 'Status', 'Candidates', 'Votes', ''].map((t) => h('th', { scope: 'col' }, t)))),
      h('tbody', {}, data.map((e) => h('tr', {},
        h('th', { scope: 'row' }, e.title),
        h('td', {}, e.scope === 'all_lgas' ? 'All LGAs' : e.lga?.name),
        h('td', { class: 'small' }, `${fmtDate(e.start_at)} – ${fmtDate(e.end_at)}`),
        h('td', {}, badge(e.status), e.results_published_at ? h('div', { class: 'small muted' }, 'Results published') : null),
        h('td', {}, String(e.candidate_count)),
        h('td', {}, `${e.votes_cast} / ${e.eligible_voters}`),
        h('td', {}, h('a', { class: 'btn btn-sm btn-outline-dark', href: `/admin/elections/${e.id}`, 'aria-label': `Manage ${e.title}` }, 'Manage'))))))));
  } catch (err) {
    clear(table);
    showError('#elections-alert', err);
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  clearFieldErrors(form);
  clear($('#election-form-alert'));
  const { payload, errors } = readElectionForm(form);
  if (errors.length) { applyFieldErrors(form, errors); return; }
  const button = $('#election-submit');
  setBusy(button, true);
  try {
    const { data } = await api.post('/admin/elections', payload);
    window.location.assign(`/admin/elections/${data.id}`);
  } catch (err) {
    const unmatched = applyFieldErrors(form, err.details);
    showAlert('#election-form-alert', 'danger', [err.message, ...unmatched].join(' '), { requestId: err.requestId });
  } finally {
    setBusy(button, false);
  }
});

setupElectionForm(form).catch((err) => showError('#elections-alert', err));
load();
