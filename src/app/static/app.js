import { initAccounts } from './account.js';
import { initClubs } from './clubs.js';

const byId = (id) => document.getElementById(id);
const state = { config: {}, account: null, clubs: [], page: 'catalog', catalogPage: 0 };
const pageSize = 24;
const filters = byId('filters');
const eventForm = byId('create');
const template = byId('event-card');
const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
let editId = null;
let catalogRequest;
let searchTimer;
let sessionRequest = 0;

async function request(path, { method = 'GET', body, signal } = {}) {
  const headers = {};
  if (state.config.demo_mode) headers['X-User-Id'] = byId('user').value;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, { method, headers, body: JSON.stringify(body), signal });
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail;
    const message = Array.isArray(detail) ? detail.map((item) => item.msg).join(' ') : detail;
    throw Object.assign(new Error(message || `Request failed (HTTP ${response.status}).`), {
      status: response.status,
    });
  }
  if (payload === null) throw new Error('The server returned an unreadable response.');
  return payload;
}

const getState = () => state;
const accounts = initAccounts({ request, refresh, getState, openPage });
const clubsUi = initClubs({
  request,
  getState,
  openAdmin(club) {
    openPage('admin');
    accounts.editClub(club);
  },
});

function show(node, text, ok = true) {
  node.textContent = text;
  node.classList.toggle('ok', ok);
  node.classList.toggle('err', !ok);
}

async function action(button, status, callback) {
  button.disabled = true;
  show(status, '');
  try {
    await callback();
  } catch (error) {
    show(status, error.message, false);
  } finally {
    button.disabled = false;
  }
}

function button(text, click, className = 'secondary') {
  const element = document.createElement('button');
  element.type = 'button';
  element.textContent = text;
  element.className = className;
  element.addEventListener('click', () => click(element));
  return element;
}

function setOptions(select, options) {
  const previous = select.value;
  select.replaceChildren(...options.map(([value, label]) => new Option(label, value)));
  if (options.some(([value]) => String(value) === previous)) select.value = previous;
}

function updateControls() {
  const role = state.account?.role;
  byId('demo-user').hidden = !state.config.demo_mode;
  byId('outbox-nav').hidden = !state.config.demo_mode;
  byId('account-button').hidden = state.config.demo_mode;
  byId('account-button').textContent = state.account ? state.account.name : 'Sign in';
  for (const nav of document.querySelectorAll('[data-role]')) nav.hidden = nav.dataset.role !== role;
  setOptions(byId('club-filter'), [['', 'All clubs'], ...state.clubs.map((club) => [club.id, club.name])]);
  const managed = state.clubs.filter((club) => role === 'organizer' && club.organizer_id === state.account.id);
  byId('event-editor').hidden = !managed.length;
  byId('catalog-layout').classList.toggle('manage-mode', managed.length > 0);
  setOptions(eventForm.elements.club_id, managed.map((club) => [club.id, club.name]));
}

async function refresh() {
  const requestId = ++sessionRequest;
  try {
    state.config = await request('/api/config');
    const [account, clubs] = await Promise.all([
      request('/api/auth/me').catch((error) => {
        if (error.status === 401) return null;
        throw error;
      }),
      request('/api/clubs'),
    ]);
    if (requestId !== sessionRequest) return;
    if (state.account?.id !== account?.id) stopEditing();
    state.account = account;
    state.clubs = clubs;
    updateControls();
    await Promise.all([loadCategories(), openPage(state.page)]);
  } catch (error) {
    show(byId('page-message'), error.message, false);
  }
}

async function openPage(page) {
  if ((page === 'registrations' && state.account?.role !== 'student')
      || (page === 'admin' && state.account?.role !== 'admin')
      || (page === 'outbox' && !state.config.demo_mode)
      || (page === 'account' && state.config.demo_mode)) page = 'catalog';
  state.page = page;
  for (const section of document.querySelectorAll('[data-page]')) section.hidden = section.dataset.page !== page;
  for (const control of document.querySelectorAll('[data-open]')) {
    if (control.dataset.open === page) control.setAttribute('aria-current', 'page');
    else control.removeAttribute('aria-current');
  }
  if (page === 'catalog') return loadEvents();
  if (page === 'registrations') return loadMine();
  if (page === 'clubs') return clubsUi.render();
  if (page === 'outbox') return loadOutbox();
  return accounts.render();
}

async function loadCategories() {
  try {
    const categories = await request('/api/events/categories');
    setOptions(byId('category-filter'), [['', 'All categories'], ...categories.map((value) => [value, value])]);
  } catch (error) {
    show(byId('page-message'), `Could not load categories: ${error.message}`, false);
  }
}

async function loadEvents() {
  clearTimeout(searchTimer);
  catalogRequest?.abort();
  const current = new AbortController();
  catalogRequest = current;
  const status = byId('event-status');
  const list = byId('events');
  const params = new URLSearchParams();
  for (const [key, value] of new FormData(filters)) {
    if (value.trim()) params.set(key, value.trim());
  }
  byId('clear-filters').hidden = !Array.from(new FormData(filters).values()).some(Boolean);
  byId('retry-events').hidden = true;
  byId('pagination').hidden = true;
  status.textContent = 'Loading events…';
  params.set('limit', pageSize + 1);
  params.set('offset', state.catalogPage * pageSize);

  try {
    const events = await request(`/api/events?${params}`, { signal: current.signal });
    if (catalogRequest !== current) return;
    if (!events.length && state.catalogPage > 0) {
      state.catalogPage -= 1;
      return loadEvents();
    }
    const hasNext = events.length > pageSize;
    const visible = events.slice(0, pageSize);
    list.replaceChildren(...visible.map((event) => catalogCard(event)));
    status.textContent = visible.length
      ? (state.catalogPage || hasNext ? `Page ${state.catalogPage + 1}` : `${visible.length} ${visible.length === 1 ? 'event' : 'events'}`)
      : params.size > 2 ? 'No events match your filters.' : 'No events yet.';
    byId('previous-page').disabled = !state.catalogPage;
    byId('next-page').disabled = !hasNext;
    byId('pagination').hidden = !state.catalogPage && !hasNext;
  } catch (error) {
    if (current.signal.aborted) return;
    status.textContent = `Could not load events: ${error.message}`;
    byId('retry-events').hidden = false;
  }
}

function eventCard(event) {
  const card = template.content.firstElementChild.cloneNode(true);
  card.querySelector('h3').textContent = event.title;
  card.querySelector('.category').textContent = event.status === 'CANCELLED' ? 'Cancelled' : event.category;
  card.querySelector('.venue').textContent = `${event.venue} · Capacity ${event.capacity}`;
  card.querySelector('.host').textContent = state.clubs.find((club) => club.id === event.club_id)?.name || `Club #${event.club_id}`;
  const time = card.querySelector('time');
  time.dateTime = event.starts_at;
  time.textContent = dateFormat.format(new Date(event.starts_at));
  const description = card.querySelector('.event-description');
  description.textContent = event.description;
  description.hidden = !event.description.trim();
  return { card, controls: card.querySelector('.button-row'), message: card.querySelector('.registration-message') };
}

function catalogCard(event) {
  const { card, controls, message } = eventCard(event);
  const account = state.account;
  if (!account || account.role === 'student' || state.config.demo_mode) {
    const register = button(account ? 'Register' : 'Sign in to register', (el) => {
      if (!account) return openPage('account');
      return action(el, message, async () => {
        const result = await request(`/api/events/${event.id}/registrations`, { method: 'POST' });
        show(message, result.message);
      });
    }, '');
    register.setAttribute('aria-label', `${register.textContent} for ${event.title}`);
    controls.append(register);
  }
  if (account?.role === 'organizer' && state.clubs.some(
    (club) => club.id === event.club_id && club.organizer_id === account.id
  )) {
    controls.append(
      button('Edit', () => editEvent(event)),
      button('Participants', () => viewParticipants(event)),
      button('Cancel event', (el) => {
        if (!window.confirm(`Cancel “${event.title}”?`)) return;
        action(el, message, async () => {
          await request(`/api/events/${event.id}`, { method: 'DELETE' });
          if (editId === event.id) stopEditing();
          show(byId('page-message'), 'Event cancelled.');
          await loadCategories();
          await loadEvents();
        });
      }, 'secondary danger'),
    );
  }
  return card;
}

function editEvent(event) {
  editId = event.id;
  for (const field of ['title', 'description', 'venue', 'category', 'capacity', 'club_id']) {
    eventForm.elements[field].value = event[field];
  }
  eventForm.elements.starts_at.value = event.starts_at.slice(0, 16);
  byId('create-heading').textContent = 'Edit event';
  byId('save-event').textContent = 'Save changes';
  byId('cancel-edit').hidden = false;
  show(byId('create-message'), '');
  eventForm.elements.title.focus();
}

function stopEditing() {
  editId = null;
  eventForm.reset();
  byId('create-heading').textContent = 'Create event';
  byId('save-event').textContent = 'Create event';
  byId('cancel-edit').hidden = true;
  show(byId('create-message'), '');
}

async function loadMine() {
  const account = state.account;
  const status = byId('registrations-status');
  const list = byId('my-registrations');
  list.replaceChildren();
  status.textContent = 'Loading registrations…';
  try {
    const entries = await request('/api/registrations/me');
    if (account !== state.account || state.page !== 'registrations') return;
    status.textContent = entries.length ? '' : 'You have no event registrations yet.';
    list.replaceChildren(...entries.map(({ event }) => {
      const { card, controls, message } = eventCard(event);
      controls.append(button('Cancel registration', (el) => {
        if (!window.confirm(`Cancel your registration for “${event.title}”?`)) return;
        action(el, message, async () => {
          await request(`/api/events/${event.id}/registrations/me`, { method: 'DELETE' });
          show(byId('page-message'), 'Registration cancelled.');
          await loadMine();
        });
      }, 'secondary danger'));
      return card;
    }));
  } catch (error) {
    status.textContent = `Could not load registrations: ${error.message}`;
  }
}

async function viewParticipants(event) {
  const dialog = byId('participants');
  const status = byId('participants-status');
  const list = byId('participant-list');
  if (!dialog.open) dialog.showModal();
  byId('participants-heading').textContent = `Participants · ${event.title}`;
  list.replaceChildren();
  show(status, 'Loading participants…');
  try {
    const participants = await request(`/api/events/${event.id}/registrations`);
    show(status, participants.length ? '' : 'No registrations yet.');
    for (const participant of participants) {
      const row = document.createElement('div');
      row.className = 'event button-row dialog-row';
      const name = document.createElement('span');
      name.textContent = participant.name;
      row.append(name, button('Remove', (el) => {
        if (!window.confirm(`Remove ${participant.name} from this event?`)) return;
        action(el, status, async () => {
          await request(`/api/events/${event.id}/registrations/${participant.student_id}`, { method: 'DELETE' });
          await viewParticipants(event);
        });
      }, 'secondary danger'));
      list.append(row);
    }
  } catch (error) {
    show(status, error.message, false);
  }
}

async function loadOutbox() {
  const status = byId('outbox-status');
  const outbox = byId('outbox');
  try {
    const rows = await request('/api/notifications');
    const body = outbox.tBodies[0];
    body.replaceChildren();
    for (const message of rows) {
      const row = body.insertRow();
      for (const value of [message.id, message.recipient_id, message.text, message.status, message.attempts]) {
        row.insertCell().textContent = value;
      }
    }
    outbox.parentElement.hidden = !rows.length;
    status.textContent = rows.length ? '' : 'No notifications yet.';
  } catch (error) {
    status.textContent = `Could not load notifications: ${error.message}`;
  }
}

for (const control of document.querySelectorAll('[data-open]')) {
  control.addEventListener('click', () => {
    show(byId('page-message'), '');
    openPage(control.dataset.open);
  });
}
byId('user').addEventListener('change', () => {
  show(byId('page-message'), '');
  refresh();
});
filters.addEventListener('input', (event) => {
  state.catalogPage = 0;
  clearTimeout(searchTimer);
  catalogRequest?.abort();
  if (event.target === byId('search')) searchTimer = setTimeout(loadEvents, 200);
  else loadEvents();
});
filters.addEventListener('submit', (event) => {
  event.preventDefault();
  loadEvents();
});
byId('clear-filters').addEventListener('click', () => {
  filters.reset();
  state.catalogPage = 0;
  byId('search').focus();
  loadEvents();
});
byId('retry-events').addEventListener('click', loadEvents);
byId('previous-page').addEventListener('click', () => {
  state.catalogPage -= 1;
  loadEvents();
});
byId('next-page').addEventListener('click', () => {
  state.catalogPage += 1;
  loadEvents();
});
byId('cancel-edit').addEventListener('click', stopEditing);
eventForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const body = Object.fromEntries(new FormData(eventForm));
  body.capacity = Number(body.capacity);
  body.club_id = Number(body.club_id);
  const status = byId('create-message');
  const id = editId;
  action(byId('save-event'), status, async () => {
    await request(id ? `/api/events/${id}` : '/api/events', {
      method: id ? 'PUT' : 'POST', body,
    });
    stopEditing();
    show(status, id ? 'Event updated.' : 'Event created.');
    await loadCategories();
    await loadEvents();
  });
});
byId('dispatch').addEventListener('click', (event) => {
  const status = byId('dispatch-message');
  action(event.currentTarget, status, async () => {
    const result = await request('/api/notifications/dispatch', { method: 'POST' });
    show(status, `Dispatcher: ${result.sent} sent, ${result.failed_attempts} failed attempts.`, !result.failed_attempts);
    await loadOutbox();
  });
});

refresh();
