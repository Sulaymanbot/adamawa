import { api, setCsrfToken } from '../api.js';
import { $, applyFieldErrors, clear, clearFieldErrors, setBusy, showAlert } from '../ui.js';

const form = $('#login-form');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  clear($('#login-alert'));
  clearFieldErrors(form);
  const email = form.email.value.trim();
  const password = form.password.value;
  const missing = [];
  if (!email) missing.push({ field: 'email', message: 'Enter your email' });
  if (!password) missing.push({ field: 'password', message: 'Enter your password' });
  if (missing.length) {
    applyFieldErrors(form, missing);
    return;
  }
  const button = $('#login-submit');
  setBusy(button, true, 'Signing in…');
  try {
    const { data } = await api.post('/auth/login', { email, password });
    setCsrfToken(data.csrf_token);
    const next = form.dataset.next;
    if (data.otp_required) {
      window.location.assign(`/login/otp${next ? `?next=${encodeURIComponent(next)}` : ''}`);
      return;
    }
    window.location.assign(next || data.redirect);
  } catch (err) {
    form.password.value = '';
    showAlert('#login-alert', 'danger', err.message, { requestId: err.requestId });
    form.password.focus();
  } finally {
    setBusy(button, false);
  }
});
