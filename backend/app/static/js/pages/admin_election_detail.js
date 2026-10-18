import { api } from '../api.js';
import { $, applyFieldErrors, badge, clear, clearFieldErrors, empty, fmtDate, h, setBusy, showAlert, showError } from '../ui.js';
import { fillElectionForm, readElectionForm, setupElectionForm } from './election_form.js';

const root = $('#election-root');
const id = root.dataset.electionId;
const form = $('#election-form');
const cForm = $('#candidate-form');
const actionModal = window.bootstrap.Modal.getOrCreateInstance($('#action-modal'));
let election = null;
let lgas = [];

// The single most important next step gets the black button; the rest are quiet.
const ACTION_INFO = {
  open: ['Open voting', 'btn-primary', 'Voters can vote between the open and close times. Details and candidates get locked.'],
  close: ['Close voting', 'btn-primary', 'No more votes will be accepted. This cannot be undone.'],
  schedule: ['Schedule', 'btn-outline-dark', 'Mark as scheduled. You can still edit it.'],
  unschedule: ['Back to draft', 'btn-quiet', 'Move back to draft.'],
  archive: ['Archive', 'btn-quiet', 'Archive this election. Results stay visible.'],
  cancel: ['Cancel election', 'btn-quiet', 'Votes in a cancelled election are never counted. Give a reason.'],
};
const ACTION_ORDER = ['open', 'close', 'schedule', 'unschedule', 'archive', 'cancel'];

function renderSummary() {
  $('#election-title').textContent = election.title;
  const stat = (label, value) => h('div', { class: 'col-6 col-md-3' },
    h('div', { class: 'stat' }, h('div', { class: 'stat-value' }, value), h('div', { class: 'stat-label' }, label)));
  clear($('#election-summary')).append(
    h('div', { class: 'd-flex flex-wrap gap-2 align-items-center mb-3' }, badge(election.status),
      election.status === 'open' ? badge(election.phase) : null,
      election.results_published_at ? badge('active', 'Results published') : null,
      h('span', { class: 'muted small' }, `${fmtDate(election.start_at)} – ${fmtDate(election.end_at)} · ${election.scope === 'all_lgas' ? 'All LGAs' : election.lga.name}`)),
    h('div', { class: 'row g-3' },
      stat('Votes', String(election.votes_cast)),
      stat('Eligible voters', String(election.eligible_voters)),
      stat('Candidates', String(election.candidate_count))));
}

function renderActions() {
  const box = clear($('#action-buttons'));
  for (const action of ACTION_ORDER.filter((a) => election.allowed_actions.includes(a))) {
    const [label, cls] = ACTION_INFO[action];
    box.append(h('button', { type: 'button', class: `btn ${cls}`, onclick: () => confirmAction(action) }, label));
  }
  if (!election.allowed_actions.length) box.append(h('span', { class: 'muted' }, 'Nothing left to do.'));

  const pub = clear($('#publish-area'));
  if (election.status === 'closed') {
    if (election.results_published_at) {
      pub.append(h('div', { class: 'd-flex flex-wrap gap-2 align-items-center' },
        h('a', { class: 'btn btn-outline-dark', href: `/results/${election.id}` }, 'View published results'),
        h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => publish(true) }, 'Hide results')));
    } else {
      pub.append(h('button', { type: 'button', class: 'btn btn-primary', onclick: () => publish(false) }, 'Publish results'));
    }
  } else if (election.results_published_at) {
    pub.append(h('a', { class: 'btn btn-outline-dark', href: `/results/${election.id}` }, 'View published results'));
  }
}

function confirmAction(action) {
  const [label, , desc] = ACTION_INFO[action];
  $('#action-title').textContent = `${label}?`;
  $('#action-desc').textContent = desc;
  $('#action-reason').value = '';
  $('#action-reason-wrap').classList.toggle('d-none', action !== 'cancel');
  clear($('#action-alert'));
  const btn = $('#action-confirm');
  btn.textContent = label;
  btn.onclick = async () => {
    setBusy(btn, true);
    try {
      const reason = $('#action-reason').value.trim();
      const { data } = await api.post(`/admin/elections/${id}/${action}`, reason ? { reason } : undefined);
      election = data;
      actionModal.hide();
      showAlert('#detail-alert', 'success', `Election is now ${data.status}.`);
      render();
    } catch (err) {
      showError('#action-alert', err);
    } finally {
      setBusy(btn, false);
    }
  };
  actionModal.show();
}

async function publish(hide) {
  try {
    const { data } = await api.post(`/admin/elections/${id}/publish-results`, { hide });
    election = data;
    showAlert('#detail-alert', 'success', hide ? 'Results hidden.' : 'Results published.');
    render();
  } catch (err) {
    showError('#detail-alert', err);
  }
}

function setFormLocked(locked) {
  form.querySelectorAll('input, select, textarea, button').forEach((el) => { el.disabled = locked; });
  $('#edit-locked').classList.toggle('d-none', !locked);
  cForm.classList.toggle('d-none', locked);
  $('#candidates-locked').classList.toggle('d-none', !locked);
}

async function loadCandidates() {
  const box = $('#candidates-table');
  try {
    const { data } = await api.get(`/admin/elections/${id}/candidates`);
    if (!data.length) { empty(box, 'No candidates yet.'); return; }
    const editable = election.editable;
    clear(box).append(h('div', { class: 'table-responsive' }, h('table', { class: 'table align-middle mb-0' },
      h('caption', { class: 'visually-hidden' }, 'Candidates'),
      h('thead', {}, h('tr', {}, ['Name', 'Party', 'LGA', 'Status', ''].map((t) => h('th', { scope: 'col' }, t)))),
      h('tbody', {}, data.map((c) => h('tr', {},
        h('th', { scope: 'row' }, c.full_name),
        h('td', {}, c.party_affiliation),
        h('td', {}, c.lga.name),
        h('td', {}, badge(c.status)),
        h('td', {}, editable ? h('div', { class: 'd-flex flex-wrap gap-1' },
          h('button', { type: 'button', class: 'btn btn-sm btn-outline-dark', 'aria-label': `Edit ${c.full_name}`, onclick: () => editCandidate(c) }, 'Edit'),
          h('button', { type: 'button', class: 'btn btn-sm btn-quiet', onclick: () => toggleCandidate(c) }, c.status === 'active' ? 'Deactivate' : 'Activate'),
          h('button', { type: 'button', class: 'btn btn-sm btn-quiet', 'aria-label': `Remove ${c.full_name}`, onclick: () => removeCandidate(c) }, 'Remove')) : '')))))));
  } catch (err) {
    showError('#candidate-alert', err);
  }
}

function resetCandidateForm() {
  cForm.reset();
  clearFieldErrors(cForm);
  $('#candidate-id').value = '';
  $('#candidate-form-title').textContent = 'Add a candidate';
  $('#candidate-submit').textContent = 'Add candidate';
  $('#candidate-cancel').classList.add('d-none');
}

function editCandidate(c) {
  $('#candidate-id').value = c.id;
  cForm.full_name.value = c.full_name;
  cForm.party_affiliation.value = c.party_affiliation;
  cForm.lga_id.value = c.lga.id;
  cForm.manifesto_summary.value = c.manifesto_summary || '';
  $('#candidate-form-title').textContent = `Edit ${c.full_name}`;
  $('#candidate-submit').textContent = 'Save candidate';
  $('#candidate-cancel').classList.remove('d-none');
  cForm.full_name.focus();
}

async function toggleCandidate(c) {
  try {
    await api.patch(`/admin/candidates/${c.id}`, { status: c.status === 'active' ? 'inactive' : 'active' });
    loadCandidates();
  } catch (err) { showError('#candidate-alert', err); }
}

async function removeCandidate(c) {
  // eslint-disable-next-line no-alert
  if (!window.confirm(`Remove ${c.full_name} from this election?`)) return;
  try {
    await api.del(`/admin/candidates/${c.id}`);
    loadCandidates();
  } catch (err) { showError('#candidate-alert', err); }
}

$('#candidate-cancel').addEventListener('click', resetCandidateForm);

cForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  clearFieldErrors(cForm);
  clear($('#candidate-alert'));
  const payload = {
    full_name: cForm.full_name.value.trim(),
    party_affiliation: cForm.party_affiliation.value.trim(),
    manifesto_summary: cForm.manifesto_summary.value.trim() || null,
  };
  if (election.scope === 'all_lgas') payload.lga_id = cForm.lga_id.value ? Number(cForm.lga_id.value) : null;
  const errors = [];
  if (payload.full_name.length < 3) errors.push({ field: 'full_name', message: 'Enter the full name' });
  if (payload.party_affiliation.length < 2) errors.push({ field: 'party_affiliation', message: 'Enter the party' });
  if (election.scope === 'all_lgas' && !payload.lga_id) errors.push({ field: 'lga_id', message: 'Choose the LGA' });
  if (errors.length) { applyFieldErrors(cForm, errors); return; }
  const candidateId = $('#candidate-id').value;
  const button = $('#candidate-submit');
  setBusy(button, true);
  try {
    if (candidateId) await api.patch(`/admin/candidates/${candidateId}`, payload);
    else await api.post(`/admin/elections/${id}/candidates`, payload);
    resetCandidateForm();
    showAlert('#candidate-alert', 'success', 'Candidate saved.');
    loadCandidates();
  } catch (err) {
    const unmatched = applyFieldErrors(cForm, err.details);
    showAlert('#candidate-alert', 'danger', [err.message, ...unmatched].join(' '), { requestId: err.requestId });
  } finally {
    setBusy(button, false);
  }
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  clearFieldErrors(form);
  clear($('#election-form-alert'));
  const { payload, errors } = readElectionForm(form);
  if (errors.length) { applyFieldErrors(form, errors); return; }
  const button = $('#election-save');
  setBusy(button, true);
  try {
    const { data } = await api.patch(`/admin/elections/${id}`, payload);
    election = data;
    showAlert('#election-form-alert', 'success', 'Changes saved.');
    render();
  } catch (err) {
    const unmatched = applyFieldErrors(form, err.details);
    showAlert('#election-form-alert', 'danger', [err.message, ...unmatched].join(' '), { requestId: err.requestId });
  } finally {
    setBusy(button, false);
  }
});

function render() {
  renderSummary();
  renderActions();
  fillElectionForm(form, election);
  setFormLocked(!election.editable);
  const single = election.scope === 'single_lga';
  $('#c-lga-wrap').classList.toggle('d-none', single);
  loadCandidates();
}

async function init() {
  try {
    lgas = await setupElectionForm(form);
    for (const lga of lgas) cForm.lga_id.append(h('option', { value: lga.id }, lga.name));
    const { data } = await api.get(`/admin/elections/${id}`);
    election = data;
    render();
  } catch (err) {
    showError('#detail-alert', err);
  }
}

init();
