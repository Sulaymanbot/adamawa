import { api } from '../api.js';
import { $, clear, empty, fmtDate, h, loading, showError } from '../ui.js';

const list = $('#results-list');

async function load() {
  loading(list);
  try {
    const { data } = await api.get('/results');
    if (!data.length) {
      empty(list, 'No results yet.');
      return;
    }
    clear(list).append(...data.map((e) => h('a', { class: 'row-card', href: `/results/${e.id}` },
      h('div', {}, h('h3', {}, e.title), h('div', { class: 'meta' }, `Closed ${fmtDate(e.end_at)}`)),
      h('span', { 'aria-hidden': 'true' }, '→'))));
  } catch (err) {
    clear(list);
    showError('#results-alert', err);
  }
}

load();
