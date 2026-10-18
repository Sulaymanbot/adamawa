// Ballot flow: choose (nothing preselected) -> review -> confirm modal -> submit.
// The selection lives only in this page's memory; it is never written to
// storage, the URL or logs, and is cleared once the vote is submitted.
import { api } from '../api.js';
import { $, clear, fmtDate, h, initials, setBusy, showAlert, showError } from '../ui.js';

const root = $('#ballot-root');
const electionId = root.dataset.electionId;
const form = $('#ballot-form');
const options = $('#ballot-options');
const review = $('#review-step');
const modalEl = $('#confirm-modal');
const modal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(modalEl) : null;

// One key per page load: a network retry re-sends the same key, so the server
// returns the original receipt instead of rejecting a "duplicate".
const idempotencyKey = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`).replace(/[^A-Za-z0-9-]/g, '');

let candidates = [];
let selected = null;

function selectedCandidate() {
  const input = form.querySelector('input[name="candidate_id"]:checked');
  return input ? candidates.find((c) => String(c.id) === input.value) : null;
}

function renderCandidates() {
  clear(options);
  candidates.forEach((c, i) => {
    const id = `cand-${c.id}`;
    const descId = `cand-desc-${c.id}`;
    const input = h('input', { class: 'form-check-input', type: 'radio', name: 'candidate_id', id, value: c.id, 'aria-describedby': descId });
    const label = h('label', { class: 'ballot-option', for: id },
      input,
      h('span', { class: 'candidate-photo', 'aria-hidden': 'true' }, initials(c.full_name)),
      h('span', {},
        h('span', { class: 'candidate-name' }, c.full_name),
        h('span', { class: 'candidate-party' }, c.party_affiliation),
        c.manifesto_summary ? h('span', { class: 'candidate-note', id: descId }, c.manifesto_summary) : h('span', { id: descId })));
    input.addEventListener('change', () => {
      options.querySelectorAll('.ballot-option').forEach((el) => el.classList.remove('selected'));
      label.classList.add('selected');
      $('#choose-error').textContent = '';
    });
    options.append(label);
    if (i === 0) input.setAttribute('aria-required', 'true');
  });
}

function showStep(step) {
  form.classList.toggle('d-none', step !== 'choose');
  review.classList.toggle('d-none', step !== 'review');
  if (step === 'review') review.focus();
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  selected = selectedCandidate();
  if (!selected) {
    $('#choose-error').textContent = 'Select one candidate to continue.';
    options.querySelector('input')?.focus();
    return;
  }
  $('#review-name').textContent = selected.full_name;
  $('#review-party').textContent = selected.party_affiliation;
  $('#confirm-name').textContent = selected.full_name;
  showStep('review');
});

$('#change-btn').addEventListener('click', () => {
  showStep('choose');
  form.querySelector('input[name="candidate_id"]:checked')?.focus();
});

modalEl.addEventListener('show.bs.modal', () => clear($('#submit-alert')));

$('#submit-vote-btn').addEventListener('click', async () => {
  if (!selected) return;
  const button = $('#submit-vote-btn');
  setBusy(button, true, 'Submitting…');
  $('#confirm-cancel').disabled = true;
  try {
    await api.post(`/elections/${encodeURIComponent(electionId)}/votes`, { candidate_id: selected.id }, { 'Idempotency-Key': idempotencyKey });
    // Forget the choice before leaving the page.
    selected = null;
    form.reset();
    clear(options);
    clear($('#review-name'));
    clear($('#confirm-name'));
    window.location.replace(`/elections/${encodeURIComponent(electionId)}/receipt?new=1`);
  } catch (err) {
    setBusy(button, false);
    $('#confirm-cancel').disabled = false;
    const prefix = err.status === 0 ? "We couldn't confirm your vote. Check your dashboard before trying again. " : '';
    showAlert('#submit-alert', 'danger', prefix + err.message, { requestId: err.requestId });
    if (err.code === 'already_voted') {
      button.disabled = true;
      setTimeout(() => window.location.assign(`/elections/${encodeURIComponent(electionId)}/receipt`), 2500);
    }
  }
});

async function load() {
  try {
    const { data } = await api.get(`/elections/${encodeURIComponent(electionId)}/ballot`);
    $('#ballot-title').textContent = data.election.title;
    $('#ballot-meta').textContent = `${data.race.lga} LGA · Closes ${fmtDate(data.election.end_at)}`;
    if (data.has_voted) {
      showAlert('#ballot-alert', 'info', "You've already voted in this election.");
      $('#ballot-alert').append(h('a', { class: 'btn btn-outline-dark', href: `/elections/${electionId}/receipt` }, 'View receipt'));
      return;
    }
    if (!data.can_vote) {
      showAlert('#ballot-alert', 'warning', data.election.phase === 'opening_soon' || data.election.status === 'scheduled'
        ? `Voting opens ${fmtDate(data.election.start_at)}.`
        : 'Voting is closed.');
      return;
    }
    candidates = data.candidates;
    $('#ballot-legend').textContent = 'Choose one candidate';
    renderCandidates();
    showStep('choose');
  } catch (err) {
    showError('#ballot-alert', err);
  }
}

if (!modal) console.warn('Bootstrap modal unavailable');
load();
