const storedUser = JSON.parse(localStorage.getItem('clinicflow_user') || 'null');
const state = { token: localStorage.getItem('clinicflow_token'), user: storedUser, page: 1, authMode: 'login', doctors: [] };
const $ = (selector) => document.querySelector(selector);

function showToast(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3200);
}

async function api(path, options = {}) {
  const headers = { ...(options.body ? {'Content-Type': 'application/json'} : {}), ...(state.token ? {Authorization: `Bearer ${state.token}`} : {}) };
  let response;
  try {
    response = await fetch(path, {...options, headers});
  } catch (error) {
    throw new Error('Something went wrong. Please try again.');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && state.token) {
      clearSession();
      openAuth();
    }
    throw new Error(data.error || 'Something went wrong. Please try again.');
  }
  return data;
}

function clearSession() {
  state.token = null;
  state.user = null;
  localStorage.removeItem('clinicflow_token');
  localStorage.removeItem('clinicflow_user');
  $('#workspace').hidden = true;
  document.querySelector('main').hidden = false;
  document.querySelector('.topbar').hidden = false;
}

function openAuth() { $('#auth-modal').hidden = false; }
function closeAuth() { $('#auth-modal').hidden = true; }
function setAuthMode(mode) {
  state.authMode = mode;
  document.querySelectorAll('[data-auth-tab]').forEach((tab) => tab.classList.toggle('active', tab.dataset.authTab === mode));
  $('#auth-title').textContent = mode === 'login' ? 'Welcome back' : 'Make space for better care';
  $('#auth-subtitle').textContent = mode === 'login' ? 'Sign in to manage today’s appointments.' : 'Create a front-desk account in a few seconds.';
  $('#auth-submit').innerHTML = mode === 'login' ? 'Sign in <span>→</span>' : 'Create account <span>→</span>';
  $('input[name="name"]').hidden = mode === 'login';
  $('input[name="name"]').required = mode === 'register';
  $('#auth-form').reset();
}

async function submitAuth(event) {
  event.preventDefault();
  const form = new FormData(event.target);
  const payload = Object.fromEntries(form.entries());
  const message = $('#auth-message'); message.textContent = '';
  try {
    if (state.authMode === 'register') await api('/api/auth/register', {method: 'POST', body: JSON.stringify(payload)});
    const result = await api('/api/auth/login', {method: 'POST', body: JSON.stringify({email: payload.email, password: payload.password})});
    state.token = result.token; state.user = result.user; localStorage.setItem('clinicflow_token', state.token); localStorage.setItem('clinicflow_user', JSON.stringify(result.user)); closeAuth(); showWorkspace(result.user); showToast('You are signed in.');
  } catch (error) { message.textContent = error.message; }
}

function showWorkspace(user) {
  $('#welcome').textContent = `Good morning, ${user.name.split(' ')[0]}`;
  $('#profile-name').textContent = user.name;
  $('#profile-avatar').textContent = user.name.trim().charAt(0).toUpperCase();
  $('#workspace').hidden = false; document.querySelector('main').hidden = true; document.querySelector('.topbar').hidden = true;
  loadDoctors(); loadAppointments();
  $('#workspace').scrollIntoView({behavior: 'smooth'});
}

async function loadDoctors() {
  const bookingSelect = $('#doctor-select');
  const scheduleSelect = $('#schedule-doctor-filter');
  const bookingSubmit = $('#booking-submit');
  const status = $('#doctor-status');
  bookingSelect.disabled = true;
  scheduleSelect.disabled = true;
  bookingSubmit.disabled = true;
  status.textContent = 'Loading doctors...';
  try {
    state.doctors = await api('/api/doctors');
    bookingSelect.innerHTML = '<option value="" selected disabled>Choose a doctor</option>' + state.doctors.map((doctor) => `<option value="${doctor.id}">${doctor.name} · ${doctor.specialty}</option>`).join('');
    scheduleSelect.innerHTML = '<option value="">All doctors</option>' + state.doctors.map((doctor) => `<option value="${doctor.id}">${doctor.name} · ${doctor.specialty}</option>`).join('');
    const hasDoctors = state.doctors.length > 0;
    bookingSelect.disabled = !hasDoctors;
    scheduleSelect.disabled = !hasDoctors;
    bookingSubmit.disabled = !hasDoctors;
    status.textContent = hasDoctors ? `${state.doctors.length} doctors available` : 'No doctors are available for booking.';
  } catch (error) {
    status.textContent = 'Doctors could not be loaded. Please try again.';
    showToast(error.message);
  }
}

function formatAppointmentSchedule(appointment) {
  const start = new Date(appointment.start_time);
  const end = new Date(appointment.end_time);
  const date = start.toLocaleDateString([], {month: 'short', day: 'numeric'});
  const timeOptions = {hour: 'numeric', minute: '2-digit'};
  const startLabel = start.toLocaleTimeString([], timeOptions);
  const endLabel = end.toLocaleTimeString([], timeOptions);
  const duration = Math.round((end - start) / 60000);
  return `${date} · ${startLabel} – ${endLabel} · ${duration} min`;
}

async function loadAppointments() {
  const params = new URLSearchParams({page: state.page, per_page: 8, sort: $('#sort-filter').value});
  if ($('#schedule-doctor-filter').value) params.set('doctor_id', $('#schedule-doctor-filter').value);
  if ($('#patient-search').value) params.set('patient_name', $('#patient-search').value);
  if ($('#day-filter').value) params.set('day', $('#day-filter').value);
  try {
    const result = await api(`/api/appointments?${params}`);
    $('#page-label').textContent = `Page ${result.pagination.page} · ${result.pagination.total} total`;
    $('#previous-page').disabled = state.page <= 1; $('#next-page').disabled = state.page * result.pagination.per_page >= result.pagination.total;
    $('#appointments-list').innerHTML = result.items.length ? result.items.map((appointment) => `<article class="appointment-card ${appointment.status === 'cancelled' ? 'cancelled' : ''}"><div class="appointment-details"><strong>${appointment.patient.name}</strong><span>${formatAppointmentSchedule(appointment)}</span><small>${appointment.doctor.name}</small></div>${appointment.status === 'scheduled' ? `<button class="cancel-button" data-cancel="${appointment.id}">Cancel</button>` : `<small class="appointment-status">Cancelled · ₹${appointment.cancellation_fee}</small>`}</article>`).join('') : '<p class="form-message">No appointments match this view.</p>';
  } catch (error) { status.textContent = error.message; showToast(error.message); }
}

async function submitBooking(event) {
  event.preventDefault(); const form = new FormData(event.target); const message = $('#booking-message'); message.textContent = '';
  try { await api('/api/appointments', {method: 'POST', body: JSON.stringify(Object.fromEntries(form.entries()))}); event.target.reset(); state.page = 1; await loadAppointments(); showToast('Appointment booked without a conflict.'); } catch (error) { message.textContent = error.message; }
}

document.querySelectorAll('[data-open-auth]').forEach((button) => button.addEventListener('click', openAuth));
document.querySelector('[data-close-auth]').addEventListener('click', closeAuth);
document.querySelectorAll('[data-auth-tab]').forEach((tab) => tab.addEventListener('click', () => setAuthMode(tab.dataset.authTab)));
$('#auth-form').addEventListener('submit', submitAuth); $('#booking-form').addEventListener('submit', submitBooking);
$('#logout').addEventListener('click', () => { clearSession(); closeAuth(); });
$('#patient-search').addEventListener('input', () => { state.page = 1; loadAppointments(); }); $('#schedule-doctor-filter').addEventListener('change', () => { state.page = 1; loadAppointments(); }); $('#day-filter').addEventListener('change', () => { state.page = 1; loadAppointments(); }); $('#sort-filter').addEventListener('change', () => { state.page = 1; loadAppointments(); });
$('#previous-page').addEventListener('click', () => { state.page -= 1; loadAppointments(); }); $('#next-page').addEventListener('click', () => { state.page += 1; loadAppointments(); });
$('#appointments-list').addEventListener('click', async (event) => { const id = event.target.dataset.cancel; if (!id) return; try { const result = await api(`/api/appointments/${id}/cancel`, {method: 'POST'}); showToast(result.cancellation_fee ? `Cancelled. Fee: ₹${result.cancellation_fee}` : 'Cancelled for free.'); loadAppointments(); } catch (error) { showToast(error.message); } });

if (state.token) { showWorkspace(state.user || {name: 'ClinicFlow user'}); }