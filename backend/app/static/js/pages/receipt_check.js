import { api } from '../api.js';
import { $, setBusy, showAlert } from '../ui.js';

const form = $('#receipt-form');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const ref = form.receipt_reference.value.trim().toUpperCase();
  if (!/^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$/.test(ref)) {
    showAlert('#receipt-alert', 'danger', 'Enter the reference in the form ABCD-EFGH-JKLM-NPQR.');
    return;
  }
  const button = form.querySelector('button');
  setBusy(button, true, 'Checking…');
  try {
    const { data } = await api.post('/receipts/verify', { receipt_reference: ref });
    if (data.recorded) {
      showAlert('#receipt-alert', 'success', `This ballot was recorded in "${data.election_title}" on ${data.cast_date}. The choice is not shown.`);
    } else {
      showAlert('#receipt-alert', 'warning', 'No ballot with this reference was found. Check the reference and try again.');
    }
  } catch (err) {
    showAlert('#receipt-alert', 'danger', err.message, { requestId: err.requestId });
  } finally {
    setBusy(button, false);
  }
});
