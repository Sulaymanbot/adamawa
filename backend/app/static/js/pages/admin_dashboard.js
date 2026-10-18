import { api } from '../api.js';
import { $, badge, clear, empty, h, loading, showError } from '../ui.js';

function card(label, value, href) {
  const kids = [h('div', { class: 'stat-value' }, String(value)), h('div', { class: 'stat-label' }, label)];
  return h('div', { class: 'col-6 col-lg-3' }, href ? h('a', { href, class: 'stat' }, ...kids) : h('div', { class: 'stat' }, ...kids));
}

async function load() {
  loading('#participation');
  try {
    const { data } = await api.get('/admin/dashboard');
    clear($('#stat-cards')).append(
      card('Verified voters', data.voters.verified, '/admin/voters?status=verified'),
      card('Waiting for approval', data.voters.pending, '/admin/voters?status=pending'),
      card('Open elections', data.open_elections, '/admin/elections'),
      card('Votes cast', data.total_votes));

    const part = $('#participation');
    if (!data.participation.length) empty(part, 'No open or closed elections.');
    else {
      clear(part).append(h('div', { class: 'table-responsive' }, h('table', { class: 'table align-middle mb-0' },
        h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'Election'), h('th', { scope: 'col' }, 'Status'),
          h('th', { scope: 'col', class: 'text-end' }, 'Votes'), h('th', { scope: 'col', class: 'text-end' }, 'Eligible'), h('th', { scope: 'col', class: 'text-end' }, 'Turnout'))),
        h('tbody', {}, data.participation.map((p) => h('tr', {},
          h('td', {}, h('a', { href: `/admin/elections/${p.election_id}` }, p.title)),
          h('td', {}, badge(p.phase)),
          h('td', { class: 'text-end' }, String(p.votes_cast)),
          h('td', { class: 'text-end' }, String(p.eligible_voters)),
          h('td', { class: 'text-end' }, p.turnout_percent === null ? '—' : `${p.turnout_percent}%`)))))));
    }

    const pending = $('#pending');
    if (!data.pending_actions.length) empty(pending, 'All done.');
    else {
      clear(pending).append(...data.pending_actions.map((a) => {
        const href = a.type === 'verify_voters' ? '/admin/voters?status=pending' : `/admin/elections/${a.election_id}`;
        return h('a', { class: 'row-card', href }, h('span', {}, a.label), a.count ? h('span', { class: 'status status-strong' }, String(a.count)) : h('span', { 'aria-hidden': 'true' }, '→'));
      }));
    }
  } catch (err) {
    clear($('#participation'));
    showError('#admin-alert', err);
  }
}

load();
