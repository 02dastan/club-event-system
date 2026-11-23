function element(tag, text = '', className = '') {
  const node = document.createElement(tag);
  node.textContent = text;
  node.className = className;
  return node;
}

export function initClubs({ request, getState, openAdmin }) {
  const page = document.getElementById('clubs-page');
  page.classList.add('panel');
  const heading = element('h2', 'Clubs');
  heading.id = 'clubs-heading';
  page.setAttribute('aria-labelledby', heading.id);
  const status = element('p', '', 'message');
  status.setAttribute('role', 'status');
  const list = element('div', '', 'events');
  page.replaceChildren(heading, status, list);
  let renderVersion = 0;

  function show(message, text, failed = false) {
    message.textContent = text;
    message.classList.toggle('err', failed);
    message.classList.toggle('ok', Boolean(text) && !failed);
  }

  async function render() {
    const version = ++renderVersion;
    const { account, clubs } = getState();
    const isCurrent = () => version === renderVersion;
    status.textContent = '';
    status.classList.remove('ok', 'err');

    if (!clubs.length) {
      list.replaceChildren(element('p', 'No clubs yet.'));
      return;
    }

    let memberships = new Set();
    list.replaceChildren(...clubs.map((club) => {
      const card = element('article', '', 'event');
      card.append(element('h3', club.name));
      if (club.description) card.append(element('p', club.description, 'event-description'));
      card.dataset.clubId = club.id;
      return card;
    }));

    if (account?.role === 'student') {
      status.textContent = 'Loading your club memberships…';
      try {
        memberships = new Set(await request('/api/clubs/memberships'));
        if (!isCurrent()) return;
        status.textContent = '';
      } catch (error) {
        if (isCurrent()) show(status, error.message, true);
        return;
      }
    }

    for (const [index, card] of [...list.children].entries()) {
      const club = clubs[index];
      const controls = element('div', '', 'button-row');
      const message = element('p', '', 'message');
      message.setAttribute('role', 'status');
      let roster;

      if (account?.role === 'student') {
        const button = element('button', memberships.has(club.id) ? 'Leave club' : 'Join club', 'secondary');
        button.type = 'button';
        button.addEventListener('click', async () => {
          const wasMember = memberships.has(club.id);
          button.disabled = true;
          show(message, '');
          try {
            await request(`/api/clubs/${club.id}/membership`, {
              method: wasMember ? 'DELETE' : 'PUT',
            });
            if (!isCurrent()) return;
            if (wasMember) memberships.delete(club.id);
            else memberships.add(club.id);
            button.textContent = wasMember ? 'Join club' : 'Leave club';
            show(message, wasMember ? 'You left this club.' : 'You joined this club.');
          } catch (error) {
            if (isCurrent()) show(message, error.message, true);
          } finally {
            button.disabled = false;
          }
        });
        controls.append(button);
      } else if (account?.role === 'organizer' && account.id === club.organizer_id) {
        roster = addRosterControls(club, controls, message, isCurrent);
      } else if (account?.role === 'admin') {
        const button = element('button', 'Edit club', 'secondary');
        button.type = 'button';
        button.addEventListener('click', () => openAdmin(club));
        controls.append(button);
      }

      if (controls.hasChildNodes()) card.append(controls, message);
      if (roster) card.append(roster);
    }
  }

  function addRosterControls(club, controls, message, isCurrent) {
    const toggle = element('button', 'View members', 'secondary');
    toggle.type = 'button';
    toggle.setAttribute('aria-expanded', 'false');
    const roster = element('div');
    roster.id = `club-roster-${club.id}`;
    roster.hidden = true;
    toggle.setAttribute('aria-controls', roster.id);
    controls.append(toggle);

    toggle.addEventListener('click', async () => {
      if (!roster.hidden) {
        roster.hidden = true;
        toggle.setAttribute('aria-expanded', 'false');
        toggle.textContent = 'View members';
        return;
      }
      roster.hidden = false;
      toggle.setAttribute('aria-expanded', 'true');
      toggle.textContent = 'Hide members';
      roster.replaceChildren(element('p', 'Loading members…'));
      show(message, '');
      toggle.disabled = true;

      try {
        const members = await request(`/api/clubs/${club.id}/members`);
        if (!isCurrent()) return;
        if (!members.length) {
          roster.replaceChildren(element('p', 'No members yet.'));
          return;
        }

        const rows = element('ul', '', 'events');
        for (const member of members) {
          const row = element('li', '', 'button-row');
          const name = element('span', member.name);
          const remove = element('button', 'Remove', 'secondary');
          remove.type = 'button';
          remove.setAttribute('aria-label', `Remove ${member.name} from ${club.name}`);
          remove.addEventListener('click', async () => {
            remove.disabled = true;
            show(message, '');
            try {
              await request(`/api/clubs/${club.id}/members/${member.id}`, { method: 'DELETE' });
              if (!isCurrent()) return;
              row.remove();
              if (!rows.children.length) roster.replaceChildren(element('p', 'No members yet.'));
              show(message, `${member.name} was removed from the club.`);
              toggle.focus();
            } catch (error) {
              if (isCurrent()) show(message, error.message, true);
            } finally {
              remove.disabled = false;
            }
          });
          row.append(name, remove);
          rows.append(row);
        }
        roster.replaceChildren(rows);
      } catch (error) {
        if (isCurrent()) {
          roster.replaceChildren();
          roster.hidden = true;
          toggle.setAttribute('aria-expanded', 'false');
          toggle.textContent = 'View members';
          show(message, error.message, true);
        }
      } finally {
        toggle.disabled = false;
      }
    });
    return roster;
  }

  return { render };
}
