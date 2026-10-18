// Shared helpers for the election create/edit form.
import { api } from '../api.js';
import { h, isoToLocalInput, localInputToIso } from '../ui.js';

export async function setupElectionForm(form) {
  const { data: lgas } = await api.get('/locations/lgas');
  for (const lga of lgas) form.lga_id.append(h('option', { value: lga.id }, lga.name));
  const toggle = () => form.querySelector('#lga-wrap').classList.toggle('d-none', form.scope.value !== 'single_lga');
  form.scope.addEventListener('change', toggle);
  toggle();
  return lgas;
}

export function fillElectionForm(form, e) {
  form.title.value = e.title;
  form.type.value = e.type;
  form.scope.value = e.scope;
  form.lga_id.value = e.lga ? e.lga.id : '';
  form.start_at.value = isoToLocalInput(e.start_at);
  form.end_at.value = isoToLocalInput(e.end_at);
  form.description.value = e.description || '';
  form.scope.dispatchEvent(new Event('change'));
}

export function readElectionForm(form) {
  const errors = [];
  const payload = {
    title: form.title.value.trim(),
    type: form.type.value,
    scope: form.scope.value,
    description: form.description.value.trim() || null,
    start_at: localInputToIso(form.start_at.value),
    end_at: localInputToIso(form.end_at.value),
  };
  if (payload.scope === 'single_lga') payload.lga_id = form.lga_id.value ? Number(form.lga_id.value) : null;
  if (payload.title.length < 3) errors.push({ field: 'title', message: 'Enter a title (at least 3 characters)' });
  if (!payload.start_at) errors.push({ field: 'start_at', message: 'Choose when voting opens' });
  if (!payload.end_at) errors.push({ field: 'end_at', message: 'Choose when voting closes' });
  if (payload.start_at && payload.end_at && new Date(payload.end_at) <= new Date(payload.start_at)) {
    errors.push({ field: 'end_at', message: 'Closing time must be after opening time' });
  }
  if (payload.scope === 'single_lga' && !payload.lga_id) errors.push({ field: 'lga_id', message: 'Choose the LGA' });
  return { payload, errors };
}
