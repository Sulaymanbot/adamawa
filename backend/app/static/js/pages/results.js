import { api } from '../api.js';
import { $, clear, h, loading, showAlert, showError } from '../ui.js';

const root = $('#results-root');
const electionId = root.dataset.electionId;
const races = $('#results-races');

const OUTCOME = {
  winner: (r) => h('p', { class: 'fw-bold' }, `Winner: ${r.winner.full_name}`),
  tie: () => h('p', { class: 'fw-bold' }, 'Tie. Resolved outside this system.'),
  withheld: () => h('p', { class: 'muted' }, 'Fewer than 3 votes. Totals hidden to protect secrecy.'),
  no_votes: () => h('p', { class: 'muted' }, 'No votes.'),
};

function stat(label, value) {
  return h('div', { class: 'col-6 col-md-3' },
    h('div', { class: 'stat' },
      h('div', { class: 'stat-value' }, value ?? '—'),
      h('div', { class: 'stat-label' }, label)));
}

function raceTable(race) {
  const caption = h('caption', { class: 'visually-hidden' }, `Results for ${race.lga.name}`);
  const rows = race.candidates.map((c) => h('tr', {},
    h('th', { scope: 'row' }, c.full_name),
    h('td', {}, c.party_affiliation),
    h('td', { class: 'text-end' }, c.votes === null ? 'withheld' : String(c.votes)),
    h('td', { class: 'text-end' }, c.percentage === null ? '—' : `${c.percentage}%`)));
  return h('div', { class: 'table-responsive' },
    h('table', { class: 'table align-middle mb-0' }, caption,
      h('thead', {}, h('tr', {},
        h('th', { scope: 'col' }, 'Candidate'), h('th', { scope: 'col' }, 'Party'),
        h('th', { scope: 'col', class: 'text-end' }, 'Votes'), h('th', { scope: 'col', class: 'text-end' }, 'Share'))),
      h('tbody', {}, rows)));
}

function raceChart(race, index) {
  if (!window.Chart || race.outcome === 'withheld' || race.outcome === 'no_votes') return null;
  const canvas = h('canvas', { id: `chart-${index}`, role: 'img', 'aria-label': `Bar chart of votes in ${race.lga.name}. The same data is in the table.` });
  const box = h('div', { class: 'chart-box mt-3' }, canvas);
  queueMicrotask(() => {
    // eslint-disable-next-line no-new
    new window.Chart(canvas, {
      type: 'bar',
      data: {
        labels: race.candidates.map((c) => c.full_name),
        datasets: [{ label: 'Votes (simulated)', data: race.candidates.map((c) => c.votes), backgroundColor: '#000000' }],
      },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, ticks: { precision: 0 } } } },
    });
  });
  return box;
}

async function load() {
  loading(races, 'Loading results…');
  try {
    const { data } = await api.get(`/elections/${encodeURIComponent(electionId)}/results`);
    $('#results-title').textContent = data.election.title;
    const s = data.summary;
    clear($('#results-summary')).append(h('div', { class: 'row g-3 mb-4' },
      stat('Ballots cast', s.ballots_cast),
      stat('Valid votes', s.valid_votes),
      stat('Eligible voters', s.eligible_voters),
      stat('Turnout', s.turnout_percent === null ? '—' : `${s.turnout_percent}%`)));
    clear(races);
    data.races.forEach((race, i) => {
      races.append(h('section', { class: 'panel section', 'aria-labelledby': `race-${i}` },
        h('h2', { class: 'h5 mb-1', id: `race-${i}` }, `${race.lga.name} LGA`),
        h('p', { class: 'small muted' }, `Valid votes in this race: ${race.total_valid_votes}`),
        OUTCOME[race.outcome](race),
        raceTable(race),
        raceChart(race, i)));
    });
  } catch (err) {
    clear(races);
    if (err.code === 'results_not_published') showAlert('#results-alert', 'info', err.message);
    else showError('#results-alert', err);
  }
}

load();
