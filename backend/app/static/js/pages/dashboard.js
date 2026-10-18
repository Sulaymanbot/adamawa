import { api } from '../api.js';
import { $, badge, clear, empty, fmtDate, h, loading, showError } from '../ui.js';

const STATUS_HELP = {
  pending: 'Waiting for an officer to approve your account.',
  verified: "You're approved and can vote.",
  rejected: 'Your registration was not approved.',
  suspended: 'Your account is suspended.',
};

const INELIGIBLE = {
  not_verified: 'You can vote once you are verified.',
  no_candidates: 'No candidates in your LGA.',
  account_inactive: 'Your account is not active.',
};

function renderProfile(me) {
  const v = me.voter;
  $('#greeting').textContent = `Hi, ${v.full_name.split(' ')[0]}`;
  clear($('#profile')).append(
    h('div', { class: 'd-flex flex-wrap align-items-center gap-2 mb-1' },
      h('span', { class: 'fw-bold' }, 'Account'), badge(v.verification_status)),
    h('p', { class: 'mb-0' }, STATUS_HELP[v.verification_status] || ''),
    v.verification_reason ? h('p', { class: 'muted mb-0' }, `Reason: ${v.verification_reason}`) : null,
    h('details', { class: 'details mt-3' },
      h('summary', {}, 'My details'),
      h('dl', { class: 'facts' },
        h('dt', {}, 'Voter ID'), h('dd', {}, v.voter_id_masked),
        h('dt', {}, 'Email'), h('dd', {}, me.email_masked),
        h('dt', {}, 'Phone'), h('dd', {}, me.phone_masked || '—'),
        h('dt', {}, 'LGA'), h('dd', {}, v.lga),
        h('dt', {}, 'Ward'), h('dd', {}, v.ward),
        h('dt', {}, 'Polling unit'), h('dd', {}, v.polling_unit))));
}

function electionAction(e) {
  const p = e.participation;
  if (p.has_voted) {
    return h('a', { class: 'btn btn-outline-dark btn-sm', href: `/elections/${e.id}/receipt` }, '✓ Voted · Receipt');
  }
  if (!p.eligible) return h('span', { class: 'muted small' }, INELIGIBLE[p.ineligible_reason] || 'Not eligible.');
  if (p.can_vote) return h('a', { class: 'btn btn-primary', href: `/elections/${e.id}` }, 'Go to ballot');
  if (e.phase === 'opening_soon' || e.status === 'scheduled') return h('span', { class: 'muted small' }, `Opens ${fmtDate(e.start_at)}`);
  if (e.results_available) return h('a', { class: 'btn btn-outline-dark btn-sm', href: `/results/${e.id}` }, 'Results');
  if (e.status === 'cancelled') return h('span', { class: 'muted small' }, 'Cancelled');
  return h('span', { class: 'muted small' }, 'Closed');
}

function renderElections(items) {
  const box = $('#elections');
  if (!items.length) {
    empty(box, 'No elections for your LGA yet.');
    return;
  }
  clear(box).append(...items.map((e) => h('article', { class: 'row-card' },
    h('div', {},
      h('h3', {}, e.title),
      h('div', { class: 'meta d-flex flex-wrap gap-2 align-items-center' }, badge(e.phase), `Closes ${fmtDate(e.end_at)}`)),
    electionAction(e))));
}

async function load() {
  loading('#profile');
  loading('#elections');
  try {
    const [{ data: me }, { data: elections }] = await Promise.all([api.get('/me'), api.get('/elections')]);
    renderProfile(me);
    renderElections(elections);
  } catch (err) {
    clear($('#profile'));
    clear($('#elections'));
    showError('#dash-alert', err);
  }
}

load();
