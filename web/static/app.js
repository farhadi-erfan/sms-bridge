'use strict';
const $ = id => document.getElementById(id);
let rows = [], selected = new Set(), signedIn = false, pending = false;
const date = (value, millis = false) => value ? new Date(value * (millis ? 1 : 1000)).toLocaleString() : 'Not reported';
const node = (tag, text, className) => { const element = document.createElement(tag); element.textContent = text; if (className) element.className = className; return element; };
function notice(text = '') { $('notice').textContent = text; }
function loginView() { signedIn = false; rows = []; selected.clear(); $('messages').replaceChildren(); $('devices').replaceChildren(); $('counts').textContent = ''; $('search').value = ''; $('email').value = ''; $('password').value = ''; $('inbox-view').hidden = true; $('login-view').hidden = false; }
async function api(route, data) {
  const response = await fetch('/dashboard/api/' + route, {method: data === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', headers: data === undefined ? {} : {'Content-Type': 'application/json'}, body: data === undefined ? undefined : JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) { if (response.status === 401 && !route.startsWith('login')) loginView(); throw Error(result.error || 'Request failed. Please retry.'); }
  return result;
}
function selection() {
  $('selected-count').textContent = selected.size ? `${selected.size} selected` : '';
  $('mark-read').disabled = $('delete').disabled = selected.size === 0 || pending;
  $('select-all').checked = rows.length > 0 && rows.every(row => selected.has(row.id));
  $('select-all').indeterminate = selected.size > 0 && !$('select-all').checked;
}
function render() {
  const list = $('messages'); list.replaceChildren();
  if (!rows.length) list.append(node('div', 'No messages here yet. New texts will appear after your phone connects.', 'empty'));
  for (const row of rows) {
    const article = node('article', '', 'message' + (row.is_read ? '' : ' unread'));
    const label = node('label', ''), check = document.createElement('input'); check.type = 'checkbox'; check.checked = selected.has(row.id); check.setAttribute('aria-label', 'Select message from ' + (row.contact_name || row.sender));
    check.addEventListener('change', () => { if (check.checked) selected.add(row.id); else selected.delete(row.id); selection(); }); label.append(check);
    const content = node('div', ''); content.append(node('h2', row.contact_name || row.sender), node('p', `${row.sender} · ${row.device} · ${date(row.received_at, true)}`, 'meta'), node('p', row.body, 'body'));
    article.append(label, content); list.append(article);
  }
  selection();
}
async function load(append = false) {
  const params = new URLSearchParams({q: $('search').value, unread: $('unread').checked ? '1' : '0', offset: append ? rows.length : 0});
  const [messages, status] = await Promise.all([api('messages?' + params), api('status')]);
  rows = append ? rows.concat(messages.messages.filter(row => !rows.some(old => old.id === row.id))) : messages.messages;
  selected = new Set([...selected].filter(id => rows.some(row => row.id === id)));
  $('more').hidden = !messages.has_more;
  $('counts').textContent = `${status.total} messages · ${status.unread} unread · Last saved ${date(status.last_sms_uploaded_at)}`;
  $('devices').replaceChildren();
  if (!status.devices.length) $('devices').append(node('p', 'No phone has connected yet. In the Android app, enter this server’s HTTPS origin and the private upload key, then enable forwarding.'));
  for (const phone of status.devices) {
    const d = phone.diagnostics;
    let text = `${phone.name} · Last check-in ${date(phone.seen_at)}`;
    if (d) text += `\nReport received ${date(phone.diagnostics_at)} · App ${d.app_version}\nForwarding ${d.forwarding_enabled ? 'enabled' : 'paused'} · SMS permission ${d.sms_permission ? 'granted' : 'missing'}\n${d.queue_count} queued · ${d.blocked_count} deferred\nLast captured ${date(d.last_capture, true)} · Last uploaded ${date(d.last_upload, true)}${d.upload_error ? '\n' + d.upload_error : ''}${d.capture_error ? '\n' + d.capture_error : ''}`;
    $('devices').append(node('div', text, 'device'));
  }
  render();
}
async function action(fn) {
  if (pending) return;
  pending = true; selection(); notice();
  try { await fn(); } catch (error) { notice(error.message); }
  finally { pending = false; selection(); }
}
$('login-form').addEventListener('submit', event => { event.preventDefault(); action(async () => {
  await api('login', {email: $('email').value, password: $('password').value}); $('password').value = ''; signedIn = true; $('login-view').hidden = true; $('inbox-view').hidden = false; await load();
}); });
$('logout').addEventListener('click', () => action(async () => { await api('logout', {}); loginView(); }));
$('refresh').addEventListener('click', () => action(() => load()));
$('search-form').addEventListener('submit', event => { event.preventDefault(); action(() => load()); });
$('unread').addEventListener('change', () => action(() => load()));
$('more').addEventListener('click', () => action(() => load(true)));
$('select-all').addEventListener('change', () => { if ($('select-all').checked) rows.slice(0,100).forEach(row => selected.add(row.id)); else selected.clear(); render(); });
async function mutate(route) {
  const ids = [...selected];
  for (let offset = 0; offset < ids.length; offset += 100) await api(route, {ids: ids.slice(offset, offset + 100)});
  selected.clear(); await load();
}
$('mark-read').addEventListener('click', () => action(() => mutate('read')));
$('delete').addEventListener('click', () => { if (confirm(`Delete ${selected.size} selected messages from this server? This cannot be undone.`)) action(() => mutate('delete')); });
setInterval(() => { if (signedIn && !pending && selected.size === 0 && !document.hidden) action(() => load()); }, 30000);
(async () => {
  try { const config = await api('config'); document.title = config.app_name; document.querySelectorAll('[data-brand]').forEach(element => { element.textContent = config.app_name; }); } catch { /* Default name remains available. */ }
  try { await api('status'); signedIn = true; $('login-view').hidden = true; $('inbox-view').hidden = false; await load(); } catch (error) { if (signedIn) notice(error.message); }
})();
