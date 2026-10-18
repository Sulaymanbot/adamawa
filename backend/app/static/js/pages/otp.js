import { api, setCsrfToken } from '../api.js';
import { $, clear, setBusy, showAlert } from '../ui.js';

const form = $('#otp-form');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  clear($('#otp-alert'));
  const code = form.code.value.trim();
  if (!/^\d{6}$/.test(code)) {
    showAlert('#otp-alert', 'danger', 'Enter the 6-digit code.');
    form.code.focus();
    return;
  }
  const button = $('#otp-submit');
  setBusy(button, true, 'Checking…');
  try {
    const { data } = await api.post('/auth/otp/verify', { code });
    setCsrfToken(data.csrf_token);
    window.location.assign(form.dataset.next || data.redirect);
  } catch (err) {
    form.code.value = '';
    showAlert('#otp-alert', 'danger', err.message, { requestId: err.requestId });
    if (['otp_session_missing'].includes(err.code)) setTimeout(() => window.location.assign('/login'), 2500);
  } finally {
    setBusy(button, false);
  }
});

$('#otp-resend').addEventListener('click', async () => {
  try {
    const { data } = await api.post('/auth/otp/request');
    showAlert('#otp-alert', 'success', data.message);
  } catch (err) {
    showAlert('#otp-alert', 'danger', err.message, { requestId: err.requestId });
  }
});
