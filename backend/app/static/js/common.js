// Loaded on every page: sign-out button.
import { api } from './api.js';

const logout = document.getElementById('logout-btn');
if (logout) {
  logout.addEventListener('click', async () => {
    logout.disabled = true;
    try {
      await api.post('/auth/logout');
    } catch {
      // Even if the request fails, leave the page; the session will expire.
    }
    window.location.assign('/');
  });
}
