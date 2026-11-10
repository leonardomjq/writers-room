// writers-room: makes SillyTavern read and play like a web novel, on a story's card only. Other chats are untouched.
//
// It adds the Play bar (Continue, 1 2 3 at a crossroads, Note, Back, Private), the book reading style with a phone
// reading mode, the writers' room's real steps while a chapter is written, and chapter headings and a "Last time"
// recap, drawn on the page only. It never writes a chapter into the chat: a chapter always arrives as SillyTavern's own
// answer to a request. A request that was lost (a locked phone) is simply sent again; the room keeps its answer.
//
// The room publishes user/files/writers-room.json (engine/story.py, publish). This page only reads it. It holds room
// steps and released chapters, never anything the player has not reached.

const NOT_RUNNING = "The writers' room isn't running. Start it with <code>python3 engine/play.py</code>.";
const STATUS_URL = '/user/files/writers-room.json';
const CARD_URL = '/user/files/writers-room-card.json';
const RESEND = '[[writers-room:resend]]';
const PLAY = '[[writers-room:play]]';
const FACTS = '[[writers-room:facts]]';
const NO_FACTS = 'A Private scene happened. Its details stay private.';
const FACTS_PROMPT = 'In two or three plain lines, give only the facts of this scene that matter to the plot: where, when, who was there, what was agreed or done. Leave out anything sexual or graphic. No quotes.';
const PROFILE = 'Author';
const TESTED_ST = ['1.19'];             // the phone reading mode reaches into SillyTavern's layout: off on anything else
const STALE_SECONDS = 120;
const AWAY_SECONDS = 8 * 3600;
const STEPS = [['planning', 'Plan'], ['writing', 'Write'], ['reading', 'Read as you'], ['mending', 'Mend'], ['checking', 'Check']];
const MAX_RETRIES = 6;
const MIN_CONTEXT = 64000;
const PENDING_KEY = 'writers-room-pending';

const ctx = () => SillyTavern.getContext();
const settings = () => {
    const all = ctx().extensionSettings;
    all.writersRoom ??= { style: true, privateProfile: '', offered: false };
    return all.writersRoom;
};

let status = null;
let bar, roomLine, buttons, notePanel;
let retrying = false;               // the next request is a resend (the interceptor marks it)
let lastTry = 0;
let lastConnect = 0;
let backArmed = 0;
let stBranchOk = false;
let pageInstalled = false;

// ---- what is on screen ----

function storyOpen() {
    const c = ctx();
    if (c.groupId || c.characterId === undefined) return false;
    return Boolean(c.characters?.[c.characterId]?.data?.extensions?.writers_room);
}

function profiles() {
    return ctx().extensionSettings.connectionManager?.profiles || [];
}

function currentProfile() {
    const cm = ctx().extensionSettings.connectionManager;
    return cm?.profiles?.find(p => p.id === cm.selectedProfile)?.name || '';
}

const onAuthor = () => currentProfile() === PROFILE;
const hasAuthor = () => profiles().some(p => p.name === PROFILE);
const generating = () => $('#mes_stop').is(':visible');

const isOoc = mes => /^\*\(Author:/.test((mes || '').trim());

function normalized(text) {
    return (text || '').toLowerCase().replace(/[^a-z0-9]+/g, '');
}

// The same start of a chapter's prose as story.py's head().
function headOf(mes) {
    const noTitle = (mes || '').trim().replace(/^#\s+[^\n]*\n/, '');
    const prose = ('\n' + noTitle).split(/\n\s*\**1[.)]\**\s/)[0];
    return normalized(prose).slice(0, 60);
}

function chapterOf(mes) {
    const head = headOf(mes);
    return head ? status?.chapters?.find(c => c.head === head) : undefined;
}

function lastStoryMessage() {
    const chat = ctx().chat || [];
    for (let i = chat.length - 1; i >= 0; i--) {
        if (!chat[i].is_user && !chat[i].is_system && !isOoc(chat[i].mes)) return chat[i];
    }
    return null;
}

function optionCount() {
    const mes = lastStoryMessage()?.mes || '';
    const found = mes.match(/^\s*\**[1-9][.)]\**\s+\S/gm) || [];
    return /^\s*\**1[.)]/m.test(mes) ? found.length : 0;
}

// ---- a chapter on its way ----

function pending() {
    try {
        return JSON.parse(localStorage.getItem(PENDING_KEY) || 'null');
    } catch {
        return null;
    }
}

function setPending(value) {
    try {
        if (value) localStorage.setItem(PENDING_KEY, JSON.stringify(value));
        else localStorage.removeItem(PENDING_KEY);
    } catch { /* a private window: it still works, without surviving a reload */ }
}

function send(text) {
    const box = $('#send_textarea');
    box.val(text);
    box[0].dispatchEvent(new Event('input', { bubbles: true }));
    $('#send_but').trigger('click');
}

// A request whose answer never came: send it again, marked, as soon as the page is awake. The room answers from what
// it kept, or goes on holding the same request, so this can never start a second chapter.
function reattach() {
    keepConnected();
    const p = pending();
    if (!p || !storyOpen() || !onAuthor() || generating() || document.visibilityState !== 'visible') return;
    if (p.chat !== ctx().getCurrentChatId() || $('#send_textarea').val() || ctx().onlineStatus === 'no_connection') return;
    if (Date.now() - lastTry < 10000 || Date.now() - p.at < 4000) return;
    if ((p.tries || 0) >= MAX_RETRIES) {
        setPending(null);
        toastr.warning("Can't reach the writers' room. Is python3 engine/play.py running?");
        render();
        return;
    }
    lastTry = Date.now();
    setPending({ ...p, tries: (p.tries || 0) + 1 });
    retrying = true;
    send('');
}

// SillyTavern opens disconnected unless the user turned on auto-connect, and then refuses to send.
function keepConnected() {
    if (!storyOpen() || !onAuthor() || ctx().onlineStatus !== 'no_connection') return;
    if (Date.now() - lastConnect < 15000) return;
    lastConnect = Date.now();
    $('#api_button_openai').trigger('click');
}

// Runs inside every generation. On the story, the request only needs the chat since the newest chapter: a long book
// stays fast on a phone and always fits. A resend gets its mark.
globalThis.writersRoomInterceptor = async function (chat, _size, _abort, type) {
    if (!storyOpen() || !onAuthor() || type === 'quiet') return;   // a background feature stays unmarked: no chapter for it
    await ensureContext();
    let from = -1;
    for (let i = chat.length - 1; i >= 0 && from < 0; i--) {
        if (!chat[i].is_user && chapterOf(chat[i].mes)) from = i;
    }
    if (from > 0) chat.splice(0, from);
    if (from >= 0) keepPrivatePrivate(chat);
    if (chat.length) chat[chat.length - 1].mes = `${chat[chat.length - 1].mes}\n\n${retrying ? RESEND : PLAY}`;
    retrying = false;
};

// A Private scene never reaches Claude or Codex: only the plain facts the player's own model gave when they stepped back.
function keepPrivatePrivate(chat) {
    const end = chat[chat.length - 1]?.is_user ? chat.length - 1 : chat.length;
    const stretch = chat.slice(1, end);
    if (!stretch.some(m => !m.is_user && !isOoc(m.mes))) return;
    const facts = ctx().chatMetadata?.writersRoomFacts || NO_FACTS;
    const notes = stretch.filter(m => isOoc(m.mes) || (m.is_user && /^\(.*\)$/s.test(m.mes.trim())));
    chat.splice(1, end - 1, { ...chat[0], mes: `${FACTS} ${facts}` }, ...notes);
}

function hasPrivateStretch() {
    const chat = ctx().chat || [];
    for (let i = chat.length - 1; i >= 0; i--) {
        if (!chat[i].is_user && chapterOf(chat[i].mes)) return false;
        if (!chat[i].is_user && !chat[i].is_system && !isOoc(chat[i].mes)) return true;
    }
    return false;
}

async function backToStory() {
    const c = ctx();
    let facts = '';
    if (hasPrivateStretch()) {
        buttons.replaceChildren(button('Reading the scene for facts...', () => {}, 'wr-main'));
        try {
            facts = await c.generateQuietPrompt({ quietPrompt: FACTS_PROMPT, responseLength: 160 });
        } catch (err) {
            console.warn('[writers-room] no facts from the Private scene', err);
        }
        c.chatMetadata.writersRoomFacts = (facts || NO_FACTS).trim().slice(0, 800);
        await c.saveMetadata();
    }
    await switchProfile(PROFILE);
}

async function ensureContext() {
    try {
        const { oai_settings } = await import('/scripts/openai.js');
        if (Number(oai_settings.openai_max_context) < MIN_CONTEXT) {
            oai_settings.openai_max_context = MIN_CONTEXT;
            oai_settings.max_context_unlocked = true;
        }
        oai_settings.stream_openai = true;
        // the room reads these requests word for word: nothing may rewrite the messages on the way
        oai_settings.custom_prompt_post_processing = '';
        if (oai_settings.names_behavior === 2) oai_settings.names_behavior = 0;
    } catch (err) {
        console.warn('[writers-room] could not set the context size', err);
    }
}

// ---- status ----

async function loadStatus() {
    try {
        const r = await fetch(`${STATUS_URL}?t=${Date.now()}`, { cache: 'no-store' });
        if (r.ok) status = await r.json();
    } catch { /* the room has not published yet */ }
}

const roomDown = () => !status || Date.now() / 1000 - (status.beat || 0) > STALE_SECONDS;

function roomText() {
    if (roomDown()) return NOT_RUNNING;
    const step = status.room?.step;
    if (!step) return "The room has your move.";
    const at = STEPS.findIndex(s => s[0] === step);
    const line = STEPS.map(([key, label], i) => `<span class="${i === at ? 'wr-now' : i < at ? 'wr-done' : ''}">${label}</span>`);
    const minutes = Math.floor((Date.now() / 1000 - (status.room.since || 0)) / 60);
    return line.join('<span class="wr-sep"> · </span>') + (minutes > 0 ? `<span class="wr-min"> ${minutes} min</span>` : '');
}

// ---- the Play bar ----

function button(label, action, cls = '') {
    const b = document.createElement('button');
    b.className = `wr-btn menu_button ${cls}`;
    b.textContent = label;
    b.addEventListener('click', action);
    return b;
}

function drawButtons() {
    buttons.replaceChildren();
    if (!hasAuthor()) {
        buttons.append(button('Connect and play', connect, 'wr-main'));
        return;
    }
    if (!onAuthor()) {
        buttons.append(button('Back to the story', backToStory, 'wr-main'));
        return;
    }
    const n = optionCount();
    if (n >= 2) {
        for (let i = 1; i <= Math.min(n, 3); i++) buttons.append(button(String(i), () => send(String(i)), 'wr-main wr-pick'));
    } else {
        buttons.append(button('Continue', () => send(''), 'wr-main'));
    }
    buttons.append(button('Note', toggleNote));
    buttons.append(button(Date.now() < backArmed ? 'Sure?' : 'Back', goBack, Date.now() < backArmed ? 'wr-armed' : ''));
    buttons.append(button('Private', togglePrivate));
}

function render() {
    const on = storyOpen();
    document.body.classList.toggle('wr-on', on);
    document.body.classList.toggle('wr-style', on && settings().style);
    setPageMode(on && settings().style);
    if (!bar) return;
    bar.classList.toggle('wr-hidden', !on);
    if (!on) return;
    const waiting = onAuthor() && (generating() || Boolean(pending()));
    const down = onAuthor() && roomDown();
    roomLine.classList.toggle('wr-hidden', !waiting && !down);
    buttons.classList.toggle('wr-hidden', waiting);
    if (waiting || down) roomLine.innerHTML = roomText();
    if (waiting) notePanel.classList.add('wr-hidden');
    else drawButtons();
    decorate();
}

// ---- Back and Note ----

async function goBack() {
    if (Date.now() >= backArmed) {
        backArmed = Date.now() + 3000;
        render();
        setTimeout(render, 3100);
        return;
    }
    backArmed = 0;
    const c = ctx();
    const chat = c.chat;
    let remove = 0;
    if (chat[chat.length - 1]?.is_user) {
        remove = 1;
    } else if (chat.length > 1) {
        remove = chat[chat.length - 2]?.is_user && chat.length > 2 ? 2 : 1;
    }
    if (!remove) {
        toastr.info('Nothing to go back to yet.');
        return render();
    }
    setPending(null);
    for (let i = 0; i < remove; i++) await c.deleteLastMessage();
    await c.saveChat();
    render();
}

function toggleNote() {
    notePanel.classList.toggle('wr-hidden');
    if (!notePanel.classList.contains('wr-hidden')) notePanel.querySelector('textarea').focus();
}

function noteText() {
    const box = notePanel.querySelector('textarea');
    const text = box.value.trim().replace(/[()]/g, '');
    box.value = '';
    notePanel.classList.add('wr-hidden');
    return text;
}

function sendNote() {
    const text = noteText();
    if (text) send(`(${text})`);
}

// The chapter written again, with the note if there is one: it goes as a note on the move that brought the chapter.
async function writeAgain() {
    const text = noteText();
    const c = ctx();
    const chat = c.chat;
    const last = chat[chat.length - 1];
    if (!last || last.is_user || chat.length < 2) return toastr.info('No chapter to write again yet.');
    const before = chat[chat.length - 2];
    await c.deleteLastMessage();
    if (before?.is_user) {
        if (text) {
            before.mes = `${before.mes.replace(/\s*\(note:[^)]*\)\s*$/i, '')} (note: ${text})`;
            await c.saveChat();
            await c.reloadCurrentChat();
        } else {
            await c.saveChat();
        }
        send('');
    } else {
        await c.saveChat();
        send(text ? `c (note: ${text})` : 'c');
    }
}

// ---- Private: the player's own model, for the scenes the author leaves at the door ----

async function runCommand(text) {
    const result = await ctx().executeSlashCommandsWithOptions(text, { handleExecutionErrors: true, handleParserErrors: true });
    return result?.pipe;
}

async function switchProfile(name) {
    await runCommand(`/profile ${name}`);
    render();
}

const privateChoices = () => profiles().filter(p => p.name !== PROFILE).map(p => p.name);

async function togglePrivate() {
    const others = privateChoices();
    if (!others.length) {
        return toastr.info('Private plays on your own model. Set it up in API Connections, save it as a connection profile, then tap Private again.', '', { timeOut: 9000 });
    }
    const name = others.includes(settings().privateProfile) ? settings().privateProfile : others[0];
    await switchProfile(name);
    toastr.info(`Private: on ${name}. Change the model under Extensions, writers-room.`, '', { timeOut: 3500 });
}

function fillPrivateChoice() {
    const box = document.getElementById('wr-private');
    if (!box) return;
    const others = privateChoices();
    const chosen = others.includes(settings().privateProfile) ? settings().privateProfile : others[0] || '';
    box.replaceChildren(...others.map(name => new Option(name, name, false, name === chosen)));
    box.disabled = !others.length;
}

// ---- connect, and open the story ----

async function connect() {
    try {
        await loadStatus();
        const port = status?.port || 5005;
        if (!hasAuthor()) {
            // keep what they had, for Private (a fresh SillyTavern's Horde default is not a model of theirs)
            if (!profiles().length && ctx().mainApi !== 'koboldhorde') await runCommand('/profile-create My model');
            await runCommand('/api custom');
            await runCommand(`/api-url api=custom connect=false http://127.0.0.1:${port}/v1`);
            await runCommand('/model quiet=true author');
            $('#api_button_openai').trigger('click');            // SillyTavern checks the connection itself
            await ensureContext();
            ctx().saveSettingsDebounced();
            await runCommand(`/profile-create ${PROFILE}`);
        } else if (!onAuthor()) {
            await switchProfile(PROFILE);
        }
        await openStory();
        toastr.success("Connected. Keep python3 engine/play.py running while you play.");
    } catch (err) {
        console.error('[writers-room] connect failed', err);
        toastr.error('Could not connect automatically. See Setup by hand in the README.');
    }
    render();
}

async function openStory() {
    const c = ctx();
    const find = name => c.characters.findIndex(ch => ch?.data?.extensions?.writers_room && ch.name === name);
    const title = status?.title;
    let index = title ? find(title) : -1;
    if (index < 0) {
        const r = await fetch(`${CARD_URL}?t=${Date.now()}`, { cache: 'no-store' });
        if (!r.ok) return;
        const card = new File([await r.blob()], 'card.json', { type: 'application/json' });
        const form = new FormData();
        form.append('avatar', card);
        form.append('file_type', 'json');
        const done = await fetch('/api/characters/import', { method: 'POST', headers: c.getRequestHeaders({ omitContentType: true }), body: form, cache: 'no-cache' });
        if (!done.ok) throw new Error(`import failed: ${done.status}`);
        await c.getCharacters();
        index = find(title);
    }
    if (index >= 0) await c.selectCharacterById(index);
}

async function offerSetup() {
    if (settings().offered || !status?.story) return;
    if (hasAuthor() && ctx().characters.some(ch => ch?.data?.extensions?.writers_room)) return;
    // after SillyTavern's own first-run screens, never under them
    for (let i = 0; i < 600 && document.querySelector('dialog[open]'); i++) await new Promise(r => setTimeout(r, 1000));
    const yes = await ctx().Popup.show.confirm('writers-room', `<p>${$('<i>').text(status.title || 'Your story').html()} is ready. Connect SillyTavern to the room and open it?</p>`);
    settings().offered = true;                    // asked and answered: a closed tab asks again next time
    ctx().saveSettingsDebounced();
    if (yes) await connect();
}

// ---- the page around the chapters (nothing here reaches the chat or a prompt) ----

// A new chapter opens at its first line, not its last.
function toChapterStart() {
    const all = document.querySelectorAll('#chat .mes');
    all[all.length - 1]?.scrollIntoView({ block: 'start' });
    if (pageMode()) window.scrollBy(0, -topBarHeight());
}

// The reader's place, kept per chat: SillyTavern jumps to the end of a chat whenever it opens one.
const placeKey = () => `writers-room-place-${ctx().getCurrentChatId()}`;
let placeReady = false, placeTimer = 0;

function topBarHeight() {
    return document.getElementById('top-bar')?.offsetHeight || 0;
}

function savePlace() {
    if (!placeReady || !storyOpen()) return;
    const edge = pageMode() ? topBarHeight() : document.getElementById('chat').getBoundingClientRect().top;
    for (const el of document.querySelectorAll('#chat .mes')) {
        const r = el.getBoundingClientRect();
        if (r.bottom > edge) {
            try {
                localStorage.setItem(placeKey(), JSON.stringify({ mes: el.getAttribute('mesid'), off: Math.round(edge - r.top) }));
            } catch { /* a private window */ }
            return;
        }
    }
}

function schedulePlace() {
    if (!placeTimer) placeTimer = setTimeout(() => { placeTimer = 0; savePlace(); }, 800);
}

function moveToPlace() {
    let place = null;
    try {
        place = JSON.parse(localStorage.getItem(placeKey()) || 'null');
    } catch { /* none */ }
    const el = place && document.querySelector(`#chat .mes[mesid="${place.mes}"]`);
    if (!el) return toChapterStart();
    el.scrollIntoView({ block: 'start' });
    const by = (place.off || 0) - (pageMode() ? topBarHeight() : 0);
    if (pageMode()) window.scrollBy(0, by);
    else document.getElementById('chat').scrollTop += by;
}

function restorePlace() {
    placeReady = false;
    if (!storyOpen()) return;
    for (const wait of [300, 900, 1600]) setTimeout(moveToPlace, wait);
    setTimeout(() => { placeReady = true; }, 2000);
}

function decorate() {
    if (!status) return;
    const chat = ctx().chat || [];
    for (const el of document.querySelectorAll('#chat .mes')) {
        const msg = chat[Number(el.getAttribute('mesid'))];
        const text = el.querySelector('.mes_text');
        if (!msg || !text || msg.is_user) continue;
        const chapter = chapterOf(msg.mes);
        const mark = text.querySelector(':scope > .wr-number');
        if (chapter && !mark) {
            const line = document.createElement('div');
            line.className = 'wr-number';
            line.textContent = `Chapter ${chapter.n}`;
            text.prepend(line);
        } else if (!chapter && mark) {
            mark.remove();
        }
    }
    document.querySelector('.wr-recap')?.remove();
    const away = Date.now() / 1000 - (status.last_at || 0) > AWAY_SECONDS;
    if (away && status.recap && !pending() && !generating()) {
        const last = document.querySelector('#chat .mes.last_mes .mes_text');
        if (last) {
            const recap = document.createElement('div');
            recap.className = 'wr-recap';
            recap.textContent = `Last time: ${status.recap}`;
            last.append(recap);
        }
    }
}

// ---- phone reading mode: the page itself scrolls, like a web-novel site ----

const PHONE = window.matchMedia('(max-width: 768px), (hover: none) and (pointer: coarse)');
const pageMode = () => document.documentElement.classList.contains('wr-page');

function setPageMode(on) {
    const wanted = on && stBranchOk && PHONE.matches;
    if (wanted && !pageInstalled) {
        try {
            installPageMode();
            pageInstalled = true;
        } catch (err) {
            console.warn('[writers-room] reading mode off', err);
            stBranchOk = false;
            return;
        }
    }
    document.documentElement.classList.toggle('wr-page', Boolean(wanted && pageInstalled));
    if (!wanted) document.documentElement.classList.remove('wr-bars-out');
}

function pageScroll(chat, form) {
    const page = () => document.scrollingElement || document.documentElement;
    const proxy = (name, get, set) => {
        const base = Object.getOwnPropertyDescriptor(Element.prototype, name);
        Object.defineProperty(chat, name, {
            configurable: true,
            get() { return pageMode() ? get() : base.get.call(chat); },
            set(value) {
                if (pageMode()) set?.(value); else base.set?.call(chat, value);
            },
        });
    };
    proxy('scrollTop', () => page().scrollTop, value => { page().scrollTop = value; });
    proxy('scrollHeight', () => page().scrollHeight);
    proxy('clientHeight', () => window.innerHeight);
    // the steady screen height, which does not change while the browser's bars shrink, so SillyTavern's resize watch on
    // the chat never moves the page under the reader
    const steady = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight');
    Object.defineProperty(chat, 'offsetHeight', {
        configurable: true,
        get() { return pageMode() ? document.documentElement.clientHeight : steady.get.call(chat); },
    });
    const visible = () => window.innerHeight - form.offsetHeight;
    const height = jQuery.cssHooks.height;
    const heightGet = height.get;
    height.get = function (elem, computed, extra) {
        if (elem !== chat || !computed || !pageMode()) return heightGet.call(this, elem, computed, extra);
        return `${extra === 'content' ? visible() : window.innerHeight}px`;
    };
    for (const name of ['scrollTo', 'scroll', 'scrollBy']) {
        const base = chat[name];
        chat[name] = (...args) => (pageMode() ? window[name](...args) : base.apply(chat, args));
    }
    const rect = chat.getBoundingClientRect;
    chat.getBoundingClientRect = () => {
        const r = rect.call(chat);
        return pageMode() ? new DOMRect(r.left, 0, r.width, visible()) : r;
    };
}

// SillyTavern's pop-up menus follow the page's scroll at every frame even while closed; each places itself when it opens.
const MENUS = ['options', 'extensionsMenu', 'export_format_popup', 'sd_dropdown'];
const cssHidden = new Map();
const menusOpen = () => MENUS.some(id => {
    const el = document.getElementById(id);
    if (!el) return false;
    const shown = el.style.display;
    if (shown) return shown !== 'none';
    if (!cssHidden.has(id)) cssHidden.set(id, getComputedStyle(el).display === 'none');
    return !cssHidden.get(id);
});

function installPageMode() {
    const chat = document.getElementById('chat');
    const form = document.getElementById('form_sheld');
    const input = document.getElementById('send_textarea');
    if (!chat || !form) throw new Error('no chat or form');
    const root = document.documentElement;
    pageScroll(chat, form);
    const topBar = document.getElementById('top-bar');
    let formHeight = -1, topHeight = -1;
    const setSizes = () => {
        const next = Math.round(form.offsetHeight - (parseFloat(getComputedStyle(form).paddingBottom) || 0));
        if (next !== formHeight) { formHeight = next; root.style.setProperty('--wr-form-h', `${next}px`); }
        const top = Math.round(topBar?.offsetHeight || 0);
        if (top !== topHeight) { topHeight = top; root.style.setProperty('--wr-top-h', `${top}px`); }
    };
    const sizes = new ResizeObserver(setSizes);
    sizes.observe(form);
    if (topBar) sizes.observe(topBar);
    setSizes();
    let keyboard = false, tapped = false;
    input?.addEventListener('pointerdown', () => { tapped = true; });
    input?.addEventListener('blur', () => { tapped = false; setKeyboard(); });
    // The bars slide out when the reader goes down and back when they scroll up, like the browser's own.
    const TURN_PX = 10;
    let out = false;
    const bars = slide => {
        if (slide === out) return;
        out = slide;
        root.classList.toggle('wr-bars-out', out);
    };
    const show = () => bars(false);
    const typing = () => document.activeElement === input && (tapped || keyboard);
    let atTop = true, atEnd = false;
    const marker = where => {
        const el = document.createElement('div');
        el.className = `wr-marker wr-marker-${where}`;
        el.setAttribute('aria-hidden', 'true');
        return el;
    };
    const topMark = marker('top'), endMark = marker('end');
    (document.getElementById('sheld') || document.body).append(topMark, endMark);
    const marks = new IntersectionObserver(entries => {
        for (const e of entries) {
            if (e.target === topMark) atTop = e.isIntersecting; else atEnd = e.isIntersecting;
        }
        if (pageMode() && (atTop || atEnd)) show();
    });
    marks.observe(topMark);
    marks.observe(endMark);
    let lastY = window.scrollY, run = 0, frame = 0;
    const turn = () => {
        frame = 0;
        const y = window.scrollY;
        const step = y - lastY;
        lastY = y;
        if (!pageMode() || atTop || atEnd || document.querySelector('.openDrawer')) { run = 0; return show(); }
        run = Math.sign(step) === Math.sign(run) ? run + step : step;
        if (run > TURN_PX && !out && !typing()) bars(true);
        else if (run < -TURN_PX) show();
    };
    window.addEventListener('scroll', event => {
        if (!pageMode() || event.target !== document) return;
        if (!menusOpen()) event.stopImmediatePropagation();
        chat.dispatchEvent(new Event('scroll'));
        if (!frame) frame = requestAnimationFrame(turn);
    }, { capture: true, passive: true });
    const view = window.visualViewport;
    let lift = 0;
    const setKeyboard = () => {
        const open = Boolean(view && pageMode() && tapped && document.activeElement === input && window.innerHeight - view.height > 60);
        if (open !== keyboard) { keyboard = open; root.classList.toggle('wr-keyboard', open); }
        const next = open ? Math.max(0, Math.round(window.innerHeight - view.height - view.offsetTop)) : 0;
        if (next !== lift) { lift = next; root.style.setProperty('--wr-kb', `${next}px`); }
        if (open) show();
    };
    view?.addEventListener('resize', setKeyboard);
    view?.addEventListener('scroll', setKeyboard);
    // a toolbar shrinking changes only the window's height; SillyTavern restyles the whole page on every resize, which
    // stutters a long chat, so a height-only resize stops here in reading mode
    let width = window.innerWidth;
    window.addEventListener('resize', event => {
        const sameWidth = window.innerWidth === width;
        width = window.innerWidth;
        if (sameWidth && pageMode()) event.stopImmediatePropagation();
    }, true);
    PHONE.addEventListener?.('change', () => { render(); setKeyboard(); show(); });
}

// ---- start ----

function buildBar() {
    bar = document.createElement('div');
    bar.id = 'wr-bar';
    bar.classList.add('wr-hidden');
    roomLine = document.createElement('div');
    roomLine.id = 'wr-room';
    buttons = document.createElement('div');
    buttons.id = 'wr-buttons';
    notePanel = document.createElement('div');
    notePanel.id = 'wr-note';
    notePanel.classList.add('wr-hidden');
    const area = document.createElement('textarea');
    area.placeholder = 'A word to the author: a question, or how the story should read from now on.';
    area.rows = 2;
    area.className = 'text_pole';
    const row = document.createElement('div');
    row.className = 'wr-note-row';
    row.append(button('Send to the author', sendNote, 'wr-main'), button('Write this chapter again', writeAgain));
    notePanel.append(area, row);
    bar.append(notePanel, roomLine, buttons);
    document.getElementById('form_sheld')?.prepend(bar);
}

function buildSettings() {
    const panel = document.createElement('div');
    panel.className = 'wr-settings';
    panel.innerHTML = `<div class="inline-drawer"><div class="inline-drawer-toggle inline-drawer-header"><b>writers-room</b>
        <div class="inline-drawer-icon fa-solid fa-circle-chevron-down down"></div></div>
        <div class="inline-drawer-content">
        <label class="checkbox_label"><input type="checkbox" id="wr-style-on"><span>Book reading style on stories</span></label>
        <label for="wr-private" class="wr-private-label">Private plays on (any connection profile of yours)</label>
        <select id="wr-private" class="text_pole"></select>
        <div id="wr-connect" class="menu_button">Connect and open the story</div></div></div>`;
    document.getElementById('extensions_settings2')?.append(panel);
    const box = panel.querySelector('#wr-style-on');
    box.checked = settings().style;
    box.addEventListener('change', () => {
        settings().style = box.checked;
        ctx().saveSettingsDebounced();
        render();
    });
    panel.querySelector('#wr-private').addEventListener('change', e => {
        settings().privateProfile = e.target.value;
        ctx().saveSettingsDebounced();
    });
    fillPrivateChoice();
    panel.querySelector('#wr-connect').addEventListener('click', connect);
}

jQuery(async () => {
    const { eventSource, eventTypes } = ctx();
    try {
        const version = await (await fetch('/version')).json();
        stBranchOk = TESTED_ST.some(v => String(version.pkgVersion || '').startsWith(`${v}.`));
    } catch { stBranchOk = false; }
    buildBar();
    buildSettings();
    await loadStatus();
    eventSource.on(eventTypes.GENERATION_STARTED, (type, _params, dryRun) => {
        if (dryRun || type === 'quiet' || !storyOpen() || !onAuthor()) return;
        setPending({ chat: ctx().getCurrentChatId(), at: Date.now(), tries: pending()?.tries || 0 });
        render();
    });
    eventSource.on(eventTypes.MESSAGE_RECEIVED, () => {
        const waited = Boolean(pending());
        setPending(null);
        render();
        if (waited && storyOpen()) for (const wait of [200, 700, 1400]) setTimeout(toChapterStart, wait);
    });
    eventSource.on(eventTypes.GENERATION_STOPPED, () => { setPending(null); render(); });
    for (const name of ['CONNECTION_PROFILE_CREATED', 'CONNECTION_PROFILE_UPDATED', 'CONNECTION_PROFILE_DELETED', 'CONNECTION_PROFILE_LOADED']) {
        if (eventTypes[name]) eventSource.on(eventTypes[name], fillPrivateChoice);
    }
    for (const name of ['CHAT_CHANGED', 'CHARACTER_MESSAGE_RENDERED', 'USER_MESSAGE_RENDERED', 'MESSAGE_UPDATED', 'MESSAGE_DELETED', 'MORE_MESSAGES_LOADED', 'GENERATION_ENDED', 'CONNECTION_PROFILE_LOADED']) {
        if (eventTypes[name]) eventSource.on(eventTypes[name], () => setTimeout(render, 50));
    }
    eventSource.on(eventTypes.CHAT_CHANGED, restorePlace);
    document.getElementById('chat')?.addEventListener('scroll', schedulePlace, { passive: true });
    window.addEventListener('scroll', schedulePlace, { passive: true });
    restorePlace();
    const awake = () => { loadStatus().then(() => { reattach(); render(); }); };
    document.addEventListener('visibilitychange', awake);
    window.addEventListener('pageshow', awake);
    setInterval(() => {
        loadStatus().then(() => { reattach(); render(); });
    }, 3000);
    eventSource.on(eventTypes.APP_READY, () => { offerSetup(); });
    render();
});
