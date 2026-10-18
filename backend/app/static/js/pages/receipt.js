import { api } from '../api.js';
import { $, clear, fmtDate, h, loading, showError } from '../ui.js';

const root = $('#receipt-root');
const electionId = root.dataset.electionId;
const body = $('#receipt-body');

async function load() {
  loading(body);
  try {
    const [{ data: status }, { data: election }] = await Promise.all([
      api.get(`/elections/${encodeURIComponent(electionId)}/participation-status`),
      api.get(`/elections/${encodeURIComponent(electionId)}`),
    ]);
    clear(body);
    if (!status.has_voted) {
      body.append(h('div', { class: 'alert alert-warning' }, "You haven't voted in this election."));
      return;
    }
    body.append(h('div', { class: 'panel', role: 'status' },
      h('div', { class: 'big-check', 'aria-hidden': 'true' }, '✓'),
      h('h1', { class: 'page-title' }, 'Vote recorded'),
      h('p', { class: 'muted' }, `${election.title} · ${fmtDate(status.cast_at)}`),
      h('p', { class: 'label mt-4' }, 'Your receipt code'),
      h('p', {}, h('span', { class: 'receipt-ref', 'aria-label': `Receipt code ${status.receipt_reference.split('').join(' ')}` }, status.receipt_reference)),
      h('p', { class: 'mb-0' }, 'Keep this code. It proves your vote was recorded but never shows your choice. ',
        h('a', { href: '/receipt-check' }, 'Check it'))));
  } catch (err) {
    clear(body);
    showError('#receipt-alert', err);
  }
}

load();
