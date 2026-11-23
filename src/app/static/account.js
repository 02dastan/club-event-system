const ROLES = [
  ['student', 'Student'],
  ['organizer', 'Organizer'],
  ['admin', 'Administrator'],
];

function roleName(role) {
  return ROLES.find(([value]) => value === role)?.[1] ?? role;
}

function status(message, text, ok = true) {
  message.textContent = text;
  message.classList.toggle('ok', !!text && ok);
  message.classList.toggle('err', !!text && !ok);
}

async function run(button, message, action) {
  if (button.disabled) return;
  button.disabled = true;
  status(message, '');
  try {
    await action();
  } catch (error) {
    status(message, error.message, false);
  } finally {
    button.disabled = false;
  }
}

function submit(form, message, action) {
  form.onsubmit = event => {
    event.preventDefault();
    const button = event.submitter ?? form.querySelector('button[type="submit"]');
    const data = Object.fromEntries(new FormData(form));
    run(button, message, () => action(data));
  };
}

function button(label, action) {
  const element = document.createElement('button');
  element.type = 'button';
  element.className = 'secondary';
  element.textContent = label;
  element.onclick = action;
  return element;
}

export function initAccounts({request, refresh, getState, openPage}) {
  document.getElementById('account-page').innerHTML = `
    <div id="account-guest" class="workspace manage-mode">
      <section class="panel" aria-labelledby="signin-heading">
        <h2 id="signin-heading">Sign in</h2>
        <form id="login-form" class="create-form">
          <label>Email <input name="email" type="email" autocomplete="username" maxlength="254" required></label>
          <label>Password <input name="password" type="password" autocomplete="current-password" required></label>
          <button type="submit">Sign in</button>
        </form>
        <p id="login-message" class="message" role="status"></p>
      </section>
      <section id="signup-panel" class="panel" aria-labelledby="signup-heading">
        <h2 id="signup-heading">Create an account</h2>
        <form id="signup-form" class="create-form">
          <label>Name <input name="name" autocomplete="name" maxlength="100" required></label>
          <label>Email <input name="email" type="email" autocomplete="email" maxlength="254" required></label>
          <label>Password <input name="password" type="password" autocomplete="new-password" minlength="12" maxlength="128" aria-describedby="password-help" required></label>
          <p id="password-help">Use at least 12 characters.</p>
          <button type="submit">Create account</button>
        </form>
        <p id="signup-message" class="message" role="status"></p>
      </section>
    </div>
    <div id="account-member" class="workspace manage-mode" hidden>
      <section class="panel" aria-labelledby="account-heading">
        <h2 id="account-heading">Your account</h2>
        <p id="account-name" class="event-details"></p>
        <p id="account-email"></p>
        <p id="organizer-request-state" class="event-details" hidden></p>
        <div class="button-row">
          <button id="organizer-request" type="button" hidden>Request organizer access</button>
          <button id="sign-out" type="button" class="secondary">Sign out</button>
        </div>
        <p id="account-message" class="message" role="status"></p>
      </section>
      <section id="telegram-panel" class="panel" aria-labelledby="telegram-heading">
        <h2 id="telegram-heading">Notifications</h2>
        <p id="telegram-state" class="event-details" role="status"></p>
        <div class="button-row">
          <button id="telegram-connect" type="button" hidden>Link Telegram</button>
          <button id="telegram-unlink" type="button" class="secondary" hidden>Switch to email</button>
          <button id="telegram-refresh" type="button" class="secondary" hidden>Check link status</button>
        </div>
        <p id="telegram-instructions" hidden>
          Open the bot and press Start to finish linking.
          <a id="telegram-link" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">Open Telegram</a>
        </p>
        <p id="telegram-message" class="message" role="status"></p>
      </section>
    </div>
    <p id="account-demo-hint" class="panel" hidden>Select a demo user in the header.</p>
  `;

  document.getElementById('admin-page').innerHTML = `
    <div class="workspace manage-mode">
      <section class="panel" aria-labelledby="admin-users-heading">
        <h2 id="admin-users-heading">Users and organizer requests</h2>
        <p id="admin-message" class="message" role="status"></p>
        <p id="admin-user-state" class="event-details" role="status"></p>
        <div id="admin-users" class="events"></div>
      </section>
      <div class="events">
        <section class="panel" aria-labelledby="admin-settings-heading">
          <h2 id="admin-settings-heading">Platform settings</h2>
          <form id="signup-setting" class="create-form">
            <label>Account sign-up
              <select name="signup_enabled">
                <option value="true">Open</option>
                <option value="false">Closed</option>
              </select>
            </label>
            <button type="submit">Save settings</button>
          </form>
          <p id="settings-message" class="message" role="status"></p>
        </section>
        <section class="panel" aria-labelledby="club-editor-heading">
          <h2 id="club-editor-heading">Create club</h2>
          <form id="club-editor" class="create-form">
            <label>Club name <input name="name" maxlength="160" required></label>
            <label>Club description <textarea name="description" maxlength="4000"></textarea></label>
            <label>Club organizer <select name="organizer_id" required></select></label>
            <div class="button-row">
              <button type="submit">Create club</button>
              <button id="cancel-club-edit" type="button" class="secondary" hidden>Cancel edit</button>
            </div>
          </form>
          <p id="club-editor-message" class="message" role="status"></p>
        </section>
      </div>
    </div>
  `;

  const $ = id => document.getElementById(id);
  const login = $('login-form');
  const signup = $('signup-form');
  const accountMessage = $('account-message');
  const telegramMessage = $('telegram-message');
  const adminMessage = $('admin-message');
  const clubMessage = $('club-editor-message');
  const settings = $('signup-setting');
  const clubEditor = $('club-editor');
  let editingClub = null;
  let selectedUserId = null;
  let revision = 0;

  function renderClubEditor(club) {
    editingClub = club;
    $('club-editor-heading').textContent = club ? 'Edit club' : 'Create club';
    clubEditor.elements.name.value = club?.name ?? '';
    clubEditor.elements.description.value = club?.description ?? '';
    clubEditor.elements.organizer_id.value = club ? String(club.organizer_id) : '';
    clubEditor.querySelector('button[type="submit"]').textContent = club ? 'Save club' : 'Create club';
    $('cancel-club-edit').hidden = !club;
    status(clubMessage, '');
  }

  function editClub(club) {
    renderClubEditor(club);
    if (getState().page !== 'admin') openPage('admin');
    clubEditor.elements.name.focus();
  }

  async function signIn(form, path, data) {
    await request(path, {method: 'POST', body: data});
    form.reset();
    await refresh();
  }

  submit(login, $('login-message'), data => signIn(login, '/api/auth/login', data));
  submit(signup, $('signup-message'), data => signIn(signup, '/api/auth/signup', data));

  $('sign-out').onclick = event => run(event.currentTarget, accountMessage, async () => {
    await request('/api/auth/logout', {method: 'POST'});
    await refresh();
  });

  $('organizer-request').onclick = event => run(event.currentTarget, accountMessage, async () => {
    await request('/api/auth/organizer-request', {method: 'POST'});
    await refresh();
    status(accountMessage, 'Organizer request sent.');
  });

  $('telegram-connect').onclick = event => run(event.currentTarget, telegramMessage, async () => {
    const link = await request('/api/notifications/telegram/link', {method: 'POST'});
    const url = new URL(link.url);
    if (url.protocol !== 'https:' || url.hostname !== 't.me') throw new Error('Could not open the Telegram link.');
    $('telegram-link').href = url.href;
    $('telegram-instructions').hidden = false;
    const minutes = Math.ceil(link.expires_in / 60);
    status(telegramMessage, `The link expires in ${minutes} minutes.`);
  });

  $('telegram-unlink').onclick = event => run(event.currentTarget, telegramMessage, async () => {
    await request('/api/notifications/telegram/link', {method: 'DELETE'});
    await loadTelegram(revision);
    status(telegramMessage, 'Future messages will be sent by email.');
  });

  $('telegram-refresh').onclick = event => run(event.currentTarget, telegramMessage, () => loadTelegram(revision));

  async function loadTelegram(currentRevision) {
    const state = $('telegram-state');
    try {
      const telegram = await request('/api/notifications/telegram');
      if (currentRevision !== revision) return;
      state.textContent = telegram.linked
        ? 'Telegram is linked as your notification channel.'
        : 'Your account email is your notification channel.';
      $('telegram-connect').hidden = !telegram.enabled || telegram.linked;
      $('telegram-unlink').hidden = !telegram.enabled || !telegram.linked;
      $('telegram-refresh').hidden = !telegram.enabled || telegram.linked;
      if (telegram.linked || !telegram.enabled) $('telegram-instructions').hidden = true;
    } catch (error) {
      if (currentRevision !== revision) return;
      state.textContent = error.message;
      $('telegram-refresh').hidden = false;
    }
  }

  submit(settings, $('settings-message'), async data => {
    await request('/api/admin/settings', {method: 'PATCH', body: {signup_enabled: data.signup_enabled === 'true'}});
    await refresh();
    status($('settings-message'), 'Settings saved.');
  });

  submit(clubEditor, clubMessage, async data => {
    const path = editingClub ? `/api/clubs/${editingClub.id}` : '/api/clubs';
    const method = editingClub ? 'PUT' : 'POST';
    await request(path, {method, body: {...data, organizer_id: Number(data.organizer_id)}});
    renderClubEditor(null);
    await refresh();
    status(clubMessage, method === 'POST' ? 'Club created.' : 'Club updated.');
  });
  $('cancel-club-edit').onclick = () => renderClubEditor(null);

  function adminCard(user, currentUser) {
    const card = document.createElement('article');
    card.className = 'event';
    const heading = document.createElement('h3');
    heading.textContent = user.name;
    const details = document.createElement('p');
    details.className = 'event-details';
    details.textContent = `${user.email} · ${roleName(user.role)}`;
    card.append(heading, details);
    if (user.organizer_request === 'pending') {
      const requestState = document.createElement('p');
      requestState.textContent = 'Organizer request pending';
      const actions = document.createElement('div');
      actions.className = 'button-row';
      for (const [approved, label] of [[true, 'Approve'], [false, 'Decline']]) {
        actions.append(button(label, event => run(event.currentTarget, adminMessage, async () => {
          await request(`/api/admin/organizer-requests/${user.id}`, {method: 'PATCH', body: {approved}});
          await refresh();
          status(adminMessage, approved ? 'Organizer approved.' : 'Request declined.');
        })));
      }
      card.append(requestState, actions);
    }

    if (user.id !== currentUser.id) {
      const form = document.createElement('form');
      form.className = 'create-form';
      const label = document.createElement('label');
      label.textContent = 'Role';
      const select = document.createElement('select');
      select.name = 'role';
      select.setAttribute('aria-label', `Role for ${user.name}`);
      for (const [value, title] of ROLES) {
        select.add(new Option(title, value, value === user.role, value === user.role));
      }
      const save = document.createElement('button');
      save.type = 'submit';
      save.className = 'secondary';
      save.textContent = 'Save role';
      label.append(select);
      form.append(label, save);
      submit(form, adminMessage, async data => {
        await request(`/api/admin/users/${user.id}`, {method: 'PATCH', body: data});
        await refresh();
        status(adminMessage, 'Role updated.');
      });
      card.append(form);
    }
    return card;
  }

  async function loadAdmin(account, currentRevision) {
    const userState = $('admin-user-state');
    const list = $('admin-users');
    if (!list.childElementCount) userState.textContent = 'Loading users…';
    try {
      const [users, setting] = await Promise.all([request('/api/admin/users'), request('/api/admin/settings')]);
      if (currentRevision !== revision) return;
      userState.textContent = users.length ? '' : 'No accounts yet.';
      list.replaceChildren(...users.map(user => adminCard(user, account)));
      settings.elements.signup_enabled.value = String(setting.signup_enabled);
      const organizer = clubEditor.elements.organizer_id;
      const previous = organizer.value || (editingClub ? String(editingClub.organizer_id) : '');
      organizer.replaceChildren(new Option('Select an organizer', ''));
      for (const user of users.filter(user => user.role === 'organizer')) {
        organizer.add(new Option(`${user.name} (${user.email})`, user.id));
      }
      organizer.value = previous;
      if (organizer.selectedIndex < 0) organizer.value = '';
    } catch (error) {
      if (currentRevision !== revision) return;
      list.replaceChildren();
      userState.textContent = error.message;
    }
  }

  function render() {
    const {account, config, page} = getState();
    const currentRevision = ++revision;
    const demoMode = config?.demo_mode;
    const userId = account?.id ?? null;
    if (selectedUserId !== userId) {
      selectedUserId = userId;
      for (const message of [accountMessage, telegramMessage, adminMessage, $('settings-message')]) status(message, '');
      $('telegram-instructions').hidden = true;
      $('telegram-link').removeAttribute('href');
      $('telegram-state').textContent = '';
      $('admin-users').replaceChildren();
      renderClubEditor(null);
    }
    $('account-demo-hint').hidden = !demoMode || !!account;
    $('account-guest').hidden = !!account || !!demoMode;
    $('account-member').hidden = !account;
    $('signup-panel').hidden = config?.signup_enabled === false;
    $('account-guest').classList.toggle('manage-mode', !$('signup-panel').hidden);
    if (!account) return;
    $('account-name').textContent = `${account.name} · ${roleName(account.role)}`;
    $('account-email').textContent = account.email;
    const pending = account.organizer_request === 'pending';
    const requestState = $('organizer-request-state');
    requestState.textContent = pending ? 'Organizer request pending'
      : account.organizer_request === 'rejected' ? 'Organizer request declined.' : '';
    requestState.hidden = !requestState.textContent;
    $('organizer-request').hidden = !!demoMode || account.role !== 'student' || pending;
    $('sign-out').hidden = !!demoMode;
    $('telegram-panel').hidden = !!demoMode;
    if (!demoMode && page === 'account') return loadTelegram(currentRevision);
    if (account.role === 'admin' && page === 'admin') return loadAdmin(account, currentRevision);
  }

  return {render, editClub};
}
