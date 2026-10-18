import { api } from '../api.js';
import { $, applyFieldErrors, clear, clearFieldErrors, h, setBusy, showAlert, showError } from '../ui.js';

const form = $('#register-form');
const lga = $('#lga_id');
const ward = $('#ward_id');
const pu = $('#polling_unit_id');

function fillSelect(select, items, placeholder) {
  clear(select).append(h('option', { value: '' }, placeholder));
  for (const item of items) select.append(h('option', { value: item.id }, item.name));
  select.disabled = items.length === 0;
}

async function loadLgas() {
  try {
    const { data } = await api.get('/locations/lgas');
    fillSelect(lga, data, 'Choose LGA');
  } catch (err) {
    showError('#register-alert', err);
  }
}

lga.addEventListener('change', async () => {
  fillSelect(ward, [], 'Pick an LGA first');
  fillSelect(pu, [], 'Pick a ward first');
  if (!lga.value) return;
  try {
    const { data } = await api.get(`/locations/lgas/${encodeURIComponent(lga.value)}/wards`);
    fillSelect(ward, data, 'Choose your ward');
  } catch (err) { showError('#register-alert', err); }
});

ward.addEventListener('change', async () => {
  fillSelect(pu, [], 'Pick a ward first');
  if (!ward.value) return;
  try {
    const { data } = await api.get(`/locations/wards/${encodeURIComponent(ward.value)}/polling-units`);
    fillSelect(pu, data, 'Choose your polling unit');
  } catch (err) { showError('#register-alert', err); }
});

// Client-side checks mirror the server rules; the server re-validates everything.
export function validate(values) {
  const errors = [];
  const name = /^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'\- ]{0,79}$/;
  if (!values.surname) errors.push({ field: 'surname', message: 'Enter your surname' });
  else if (!name.test(values.surname)) errors.push({ field: 'surname', message: 'Use letters, spaces, hyphens or apostrophes only' });
  if (!values.first_name) errors.push({ field: 'first_name', message: 'Enter your first name' });
  else if (!name.test(values.first_name)) errors.push({ field: 'first_name', message: 'Use letters, spaces, hyphens or apostrophes only' });
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email)) errors.push({ field: 'email', message: 'Enter a valid email address' });
  const phone = values.phone.replace(/[\s\-().]/g, '').replace(/^\+/, '');
  const national = phone.startsWith('234') ? phone.slice(3) : phone.startsWith('0') ? phone.slice(1) : phone;
  if (!/^[789]\d{9}$/.test(national)) errors.push({ field: 'phone', message: 'Enter a valid Nigerian mobile number, e.g. 0803 123 4567' });
  if (!/^[A-Z0-9]{10,20}$/.test(values.voter_id.replace(/[\s-]/g, '').toUpperCase())) errors.push({ field: 'voter_id', message: 'Voter ID must be 10–20 letters or digits' });
  if (!values.lga_id) errors.push({ field: 'lga_id', message: 'Choose your LGA' });
  if (!values.ward_id) errors.push({ field: 'ward_id', message: 'Choose your ward' });
  if (!values.polling_unit_id) errors.push({ field: 'polling_unit_id', message: 'Choose your polling unit' });
  if (values.password.length < 10 || !/[A-Za-z]/.test(values.password) || !/\d/.test(values.password)) {
    errors.push({ field: 'password', message: 'At least 10 characters with a letter and a number' });
  }
  if (values.password !== values.confirm_password) errors.push({ field: 'confirm_password', message: 'Passwords do not match' });
  if (!values.demo_acknowledged) errors.push({ field: 'demo_acknowledged', message: 'Please confirm you understand this is a demo' });
  return errors;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  clear($('#register-alert'));
  clearFieldErrors(form);
  const values = {
    surname: form.surname.value.trim(),
    first_name: form.first_name.value.trim(),
    other_names: form.other_names.value.trim() || null,
    email: form.email.value.trim(),
    phone: form.phone.value.trim(),
    voter_id: form.voter_id.value.trim(),
    lga_id: form.lga_id.value,
    ward_id: form.ward_id.value,
    polling_unit_id: form.polling_unit_id.value,
    password: form.password.value,
    confirm_password: form.confirm_password.value,
    demo_acknowledged: form.demo_acknowledged.checked,
  };
  const errors = validate(values);
  if (errors.length) {
    applyFieldErrors(form, errors);
    showAlert('#register-alert', 'danger', `Please fix ${errors.length} field${errors.length > 1 ? 's' : ''} below.`);
    return;
  }
  const payload = { ...values, lga_id: Number(values.lga_id), ward_id: Number(values.ward_id), polling_unit_id: Number(values.polling_unit_id) };
  const button = $('#register-submit');
  setBusy(button, true, 'Submitting…');
  try {
    const { data } = await api.post('/auth/register', payload);
    form.reset();
    form.classList.add('d-none');
    $('#register-next').textContent = data.next_steps;
    const success = $('#register-success');
    success.classList.remove('d-none');
    success.focus();
  } catch (err) {
    const unmatched = applyFieldErrors(form, err.details);
    showAlert('#register-alert', 'danger', [err.message, ...unmatched].join(' '), { requestId: err.requestId });
  } finally {
    setBusy(button, false);
  }
});

loadLgas();
