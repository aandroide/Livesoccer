#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LiveSoccerTV scraper per MandraKodi (bypass Cloudflare con Playwright).

Legge le pagine competizione di livesoccertv.com e genera:
  output/<slug>.json      formato MandraKodi (SetViewMode + items)
  output/all_events.json  dati strutturati per il matching con canali.json
  output/eventi.json      versione minima: competizione, titolo, data, ora (solo partite da giocare o in corso)

Struttura reale della pagina (verificata su HTML salvato):
  tr.drow                       intestazione del giorno
  tr.matchrow                   una partita, id = id evento, data-timer = FT / minuto / vuoto
    span.ts[dv]                 kickoff in epoch millisecondi UTC (indipendente dal fuso)
    td.matchcol a[href*=/match/]  titolo "Casa - Ospite", <score> se giocata
    .mchannels a[href*=/channels/]  canali; se e' solo "Disponibile on-demand" non ci sono canali

Uso locale (Windows/Linux):
  pip install -r requirements.txt
  playwright install chromium
  python livesoccertv_scraper.py --debug

Variabili ambiente:
  HEADLESS=0        browser visibile (sotto xvfb in Actions e' piu' affidabile)
  BROWSER_CHANNEL   chrome (default, usa Google Chrome vero) oppure chromium
  PROXY_SERVER      indirizzo di un proxy con IP italiano, es. "http://utente:password@host:porta".
                     Senza questa variabile, livesoccertv.com mostra i canali del paese da cui
                     arriva la richiesta: da un runner GitHub (Stati Uniti) le partite con diritti
                     venduti anche all'estero (soprattutto Serie A) escono con i canali sbagliati.
  OUT_DIR           cartella output (default output)

Opzioni:
  --only serie-b    esegue una sola competizione
  --debug           salva l'HTML in debug/ e stampa le prime righe grezze
  --html file.html  prova il parser su un HTML salvato
"""
import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

BASE = "https://www.livesoccertv.com"

# Aggiungere qui altri campionati: slug, nome mostrato, path della pagina
COMPETITIONS = [
    # channels_from_match_page: apre anche la pagina della singola partita e legge il blocco
    # dati strutturati (ld+json), che elenca i canali di tutti i paesi gia' etichettati per
    # nazione: da li' si prende solo "Italy", cosi' il risultato non dipende da dove gira lo
    # scraper (vedi normalize/fetch_match_channels_it per il motivo per cui serve).
    {"slug": "serie-a", "name": "Serie A", "path": "/it/competitions/italy/serie-a/", "channels_from_match_page": True},
    {"slug": "serie-b", "name": "Serie B", "path": "/it/competitions/italy/serie-b/", "channels_from_match_page": True},
    {"slug": "serie-c", "name": "Serie C", "path": "/it/competitions/italy/lega-pro-1/", "channels_from_match_page": True},
    # Coppe europee e nazionale: diritti venduti in tutto il mondo, quindi i canali
    # italiani vanno sempre letti dalla pagina della singola partita.
    # I nomi coincidono con quelli di Virgilio Sport, cosi' il calendario unico
    # riconosce e unisce le stesse partite.
    {"slug": "champions-league", "name": "UEFA Champions League", "path": "/it/competitions/international/uefa-champions-league/", "channels_from_match_page": True},
    {"slug": "europa-league", "name": "UEFA Europa League", "path": "/it/competitions/international/uefa-europa-league/", "channels_from_match_page": True},
    {"slug": "conference-league", "name": "UEFA Conference League", "path": "/it/competitions/international/uefa-europa-conference-league/", "channels_from_match_page": True},
    {"slug": "nations-league", "name": "UEFA Nations League", "path": "/it/competitions/international/uefa-nations-league/", "channels_from_match_page": True},
]

# La pagina della singola partita si apre solo per le partite dei prossimi giorni:
# le coppe e la Nations League elencano molte partite, e aprirle tutte allungherebbe
# troppo il giro dell'action. Le partite piu' lontane restano con i canali della
# pagina campionato e vengono completate nei giri successivi, quando si avvicinano.
MATCH_PAGE_DAYS = int(os.environ.get("MATCH_PAGE_DAYS", "7"))

TARGET_TZ = "Europe/Rome"
OUT_DIR = os.environ.get("OUT_DIR", "output")
DEBUG_DIR = os.environ.get("DEBUG_DIR", "debug")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
BROWSER_CHANNEL = os.environ.get("BROWSER_CHANNEL", "chrome")
# Indirizzo di un proxy con IP italiano, es. "http://utente:password@host:porta". Facoltativo:
# di norma resta vuoto e non si tocca. Serve solo se un giorno si decide di avere anche i canali
# italiani per la Serie A (vedi nota sotto); finche' resta vuoto lo scraper si collega con l'IP
# normale del runner e va bene cosi'.
PROXY_SERVER = os.environ.get("PROXY_SERVER", "")

# Nota su Serie A: livesoccertv.com mostra canali diversi secondo il paese di chi si collega.
# Da un runner GitHub (Stati Uniti) la Serie A, che ha diritti venduti anche all'estero, esce con
# i canali del Nord/Centro America (Paramount+, Disney+, fuboTV, ecc.) invece di DAZN/Sky Italia.
# Scelta presa il 23/09/2026: va bene cosi'. In Italia la Serie A si sa gia' che e' su DAZN e Sky,
# quindi il dato estero e' un'informazione in piu' invece che un problema da correggere. Serie B
# e C non hanno questo comportamento (i loro diritti sono solo italiani) e restano corrette da
# qualunque IP. Se in futuro si volesse comunque il dato italiano anche per la Serie A, la strada
# e' impostare PROXY_SERVER con un proxy vero con IP italiano, non un filtro sui nomi dei canali.

THUMB = "https://i.imgur.com/7wR0JXI.png"

GIORNI = ["Lunedi", "Martedi", "Mercoledi", "Giovedi", "Venerdi", "Sabato", "Domenica"]
MESI = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio",
        "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]

FINISHED_TIMERS = {"FT", "AET", "PEN"}
LIVE_TIMERS = {"HT", "ET", "BT", "P"}

EXTRACT_JS = r"""
() => {
  const txt = el => (el ? (el.textContent || '') : '').replace(/\s+/g, ' ').trim();
  const out = [];
  document.querySelectorAll('tr.matchrow').forEach(tr => {
    const a = tr.querySelector('td.matchcol a[href*="/match/"]');
    if (!a) return;
    const ts = tr.querySelector('.ts[dv]');
    const channels = Array.from(tr.querySelectorAll('.mchannels a[href*="/channels/"]')).map(c => {
      const t = c.getAttribute('title') || '';
      return {
        name: txt(c) || t.replace(/\s*\(.*\)\s*$/, ''),
        url: c.href,
        stream: /live stream/i.test(t),
        slug: ((c.getAttribute('href') || '').match(/\/channels\/([^/]+)/) || [])[1] || ''
      };
    });
    out.push({
      id: tr.id || '',
      ko: tr.getAttribute('data-ko') || '',
      dv: ts ? (ts.getAttribute('dv') || '') : '',
      timer: (tr.getAttribute('data-timer') || '').trim(),
      title: a.getAttribute('title') || '',
      text: txt(a),
      score: txt(a.querySelector('score')),
      url: a.href,
      channels: channels
    });
  });
  return out;
}
"""

# Legge i canali italiani dalla pagina di una singola partita, con due metodi in ordine:
#  1. la tabella "Copertura internazionale" (classe "ichannels"), che elenca ogni paese con
#     i suoi canali: presente su ogni pagina partita vista finora (verificato sia su partite
#     che hanno anche il blocco dati sotto, sia su partite che non ce l'hanno).
#  2. il blocco dati strutturati <script type="application/ld+json"> (SEO), usato come
#     ripiego perche' non compare su tutte le pagine partita (es. Internazionale-Parma non
#     ce l'ha affatto, pur avendo la tabella).
# Entrambi elencano i paesi gia' etichettati per nome, quindi in teoria non cambiano secondo
# il paese di chi visita la pagina, a differenza della lista canali mostrata a video.
MATCH_CHANNELS_JS = r"""
() => {
  // risultato.italia: solo i canali italiani (quelli mostrati di default nella wiki).
  // risultato.mondo: un elenco {paese, canali} per ogni paese della tabella, Italia inclusa,
  // per il pulsante "Altri paesi" che mostra dove si vede la partita nel resto del mondo.
  const risultato = { italia: null, mondo: [] };

  const rows = Array.from(document.querySelectorAll('table.ichannels tr'));
  for (const tr of rows) {
    const flagEl = tr.querySelector('td span.flag');
    const cells = tr.querySelectorAll('td');
    if (!flagEl || cells.length < 2) continue;
    const paese = (flagEl.textContent || '').trim();
    const canali = Array.from(cells[1].querySelectorAll('a'))
      .map(a => (a.textContent || '').trim())
      .filter(Boolean);
    if (!paese || !canali.length) continue;
    if (flagEl.classList.contains('italy') && !risultato.italia) risultato.italia = canali;
    risultato.mondo.push({ paese, canali });
  }

  if (!risultato.italia) {
    // ripiego: blocco dati strutturati ld+json, non presente su tutte le pagine partita
    const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
    for (const s of scripts) {
      try {
        const data = JSON.parse(s.textContent);
        const graph = Array.isArray(data['@graph']) ? data['@graph'] : [data];
        const italia = [];
        for (const item of graph) {
          if (item['@type'] !== 'BroadcastEvent') continue;
          const pub = item.publishedOn || {};
          const area = pub.areaServed && pub.areaServed.name;
          if (area === 'Italy' || area === 'Italia') {
            if (pub.name) italia.push(pub.name);
          }
        }
        if (italia.length) { risultato.italia = italia; break; }
      } catch (e) { /* prova il prossimo blocco */ }
    }
  }

  return (risultato.italia || risultato.mondo.length) ? risultato : null;
}
"""




def log(msg):
    print(msg, flush=True)


def warn(msg):
    """Riga di avviso: in GitHub Actions compare come annotazione gialla nel riepilogo del run."""
    print(f"::warning::{msg}", flush=True)


def row_kickoff(r):
    """L'orario di calcio d'inizio di una riga grezza, o None se manca/e' malformato."""
    try:
        return datetime.fromtimestamp(int(r["dv"]) / 1000, tz=ZoneInfo(TARGET_TZ))
    except (ValueError, KeyError, TypeError):
        return None


def drop_replays(rows):
    """Visto da un IP estero (runner GitHub negli Stati Uniti) il sito aggiunge le repliche
    dei canali di quel paese come righe separate: stessa pagina partita, ma un id diverso
    dopo il # e l'orario della replica (es. Italia-Belgio del 25 riproposta il 26 alle 13:30).
    Per ogni partita teniamo solo la riga con l'orario piu' vicino alla partita vera, cioe'
    la prima."""
    best = {}
    for r in rows:
        key = (r.get("url") or "").split("#", 1)[0] or r.get("id") or id(r)
        try:
            dv = int(r.get("dv") or 0)
        except ValueError:
            dv = 0
        if key not in best or (dv and dv < int(best[key].get("dv") or 0)):
            best[key] = r
    kept = list(best.values())
    if len(kept) < len(rows):
        log(f"Repliche scartate: {len(rows) - len(kept)}")
    return kept


# Elenco dei canali italiani preso dal menu "Canali > Italia" della pagina /it/ (e' lo
# stesso da qualunque paese si visiti il sito). Serve per tenere dalla lista della
# competizione solo i canali italiani: visti dall'estero gli altri sono quelli del paese
# del runner (Paramount+, Fox, fuboTV...). Il segno "homech" del sito NON e' affidabile:
# a seconda di come il sito riconosce il visitatore marca come "di casa" anche Paramount+.
ITALIAN_CHANNEL_SLUGS = set()

ITALIAN_MENU_JS = r"""
() => {
  const out = [];
  document.querySelectorAll('li.channels .dropdown h5').forEach(h => {
    if (!h.querySelector('.flag.italy')) return;
    let ul = h.nextElementSibling;
    while (ul && ul.tagName !== 'UL') ul = ul.nextElementSibling;
    if (!ul) return;
    ul.querySelectorAll('a[href*="/channels/"]').forEach(a => {
      const m = (a.getAttribute('href') || '').match(/\/channels\/([^/]+)/);
      if (m) out.push(m[1]);
    });
  });
  return out;
}
"""

ITALIAN_NAME_RX = re.compile(
    r"(\brai\b|raiplay|sky sport(?!s)|sky go|now tv|dazn italia|^dazn ?1$|mediaset|infinity|"
    r"italia 1|canale 5|rete 4|\btv8\b|\bcielo\b|\bla7\b|sportitalia|\bnove\b|lab channel)", re.I)
FOREIGN_NAME_RX = re.compile(
    r"(germany|deutschland|spain|espa|switzerland|austria|uk\b|canada|usa|mexico|caribbean|"
    r"brazil|argentina|france|portugal|japan|arabia)", re.I)


def learn_italian_channels(page):
    try:
        found = page.evaluate(ITALIAN_MENU_JS) or []
        ITALIAN_CHANNEL_SLUGS.update(found)
    except Exception:
        pass


def is_italian_channel(c):
    slug = (c.get("slug") or "").lower()
    name = (c.get("name") or "").strip()
    if FOREIGN_NAME_RX.search(name) or FOREIGN_NAME_RX.search(slug):
        return False
    if slug and slug in ITALIAN_CHANNEL_SLUGS:
        return True
    if "italy" in slug or "italia" in slug or "italia" in name.lower():
        return True
    return bool(ITALIAN_NAME_RX.search(name))


def row_is_relevant(r, now):
    """Vale quanto il controllo dentro normalize(): scarta solo le partite finite da piu'
    di 12 ore. Usata anche prima di aprire la pagina di dettaglio di una partita, per non
    sprecare una richiesta in piu' su una partita che verrebbe comunque tolta dopo."""
    kick = row_kickoff(r)
    if kick is None:
        return False
    timer = (r.get("timer") or "").strip()
    finished = timer.upper() in FINISHED_TIMERS
    return not (finished and now - kick > timedelta(hours=12))


def wait_challenge_with_click(page, seconds=30):
    """Come cloudflare_wait, ma prova anche a cliccare il riquadro di verifica (Turnstile)
    ogni pochi secondi, esattamente come gia' fa wait_for_rows per la pagina campionato: a
    volte la verifica non passa da sola col solo attendere, serve il clic. Senza il clic
    ogni pagina resta bloccata per l'intera attesa e fallisce, come successo a tutte le
    partite di Serie A in un run (vedi log del 23/09/2026, sempre 32s esatti a fallire)."""
    for i in range(seconds):
        if not is_challenge(page):
            return True
        if i and i % 5 == 0:
            try_click_turnstile(page)
        page.wait_for_timeout(1000)
    return not is_challenge(page)


def fetch_match_channels_it(ctx, url, timeout=45000):
    """Apre la pagina di una singola partita e restituisce {"italia": [...], "mondo": [...]}
    letti dalla tabella "Copertura internazionale" (vedi MATCH_CHANNELS_JS), o None se non
    trova nulla/qualcosa va storto (in quel caso il chiamante tiene i canali gia' letti
    dalla pagina campionato). Ad aprire tante pagine di fila ogni tanto compare la verifica
    di sicurezza di Cloudflare: senza aspettare che passi (e provare a cliccarla, vedi
    wait_challenge_with_click), si leggerebbe la pagina di verifica invece della partita
    vera, che non ha questa tabella, e il risultato sembrerebbe un errore quando non lo e'."""
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        if is_challenge(page) and not wait_challenge_with_click(page, seconds=30):
            log(f"  canali IT: verifica di sicurezza non superata per {url}")
            return None
        try:
            page.wait_for_selector("table.ichannels", timeout=10000)
        except Exception:
            pass
        dati = page.evaluate(MATCH_CHANNELS_JS)
        if not (dati and dati.get("italia")):
            # a volte la tabella non e' ancora completa: si riprova dopo qualche secondo
            page.wait_for_timeout(3000)
            dati2 = page.evaluate(MATCH_CHANNELS_JS)
            if dati2 and (dati2.get("italia") or len(dati2.get("mondo", [])) > len((dati or {}).get("mondo", []))):
                dati = dati2
        return dati
    except Exception as e:
        log(f"  canali IT non letti per {url}: {str(e).splitlines()[0] if str(e) else repr(e)}")
        return None
    finally:
        page.close()


def normalize(raw_rows, comp, now):
    events = []
    tz = ZoneInfo(TARGET_TZ)
    for r in raw_rows:
        try:
            kick = datetime.fromtimestamp(int(r["dv"]) / 1000, tz=tz)
        except (ValueError, KeyError, TypeError):
            continue

        timer = (r.get("timer") or "").strip()
        finished = timer.upper() in FINISHED_TIMERS
        if finished and now - kick > timedelta(hours=12):
            continue
        if timer and not finished:
            live = timer[0].isdigit() or timer.upper() in LIVE_TIMERS
        else:
            live = (not finished) and kick <= now <= kick + timedelta(hours=2, minutes=30)

        parts = [p.strip() for p in (r.get("title") or "").split(" - ", 1)]
        if len(parts) == 2 and all(parts):
            home, away = parts
        else:
            home, away = (r.get("text") or "").strip(), ""
        title = f"{home} vs {away}" if away else home

        sc = (r.get("score") or "").replace(" ", "")
        score = sc.replace("-", ":") if sc else ""

        seen, channels = set(), []
        for c in r.get("channels", []):
            if c["name"] and c["name"] not in seen:
                seen.add(c["name"])
                channels.append(c)

        events.append({
            "id": r.get("id") or r["url"],
            "competition": comp["name"],
            "home": home,
            "away": away,
            "title": title,
            "kickoff": kick.isoformat(),
            "date": kick.strftime("%Y-%m-%d"),
            "time": kick.strftime("%H:%M"),
            "status": "finished" if finished else "live" if live else "upcoming",
            "score": score,
            "match_url": r["url"],
            "channels": channels,
            "canali_mondo": r.get("canali_mondo", []),
        })
    events.sort(key=lambda e: e["kickoff"])
    return events


def build_kodi_json(comp, events):
    items = [{
        "title": f"[COLOR gold]=== {comp['name'].upper()} ===[/COLOR]",
        "link": "ignoreme",
        "thumbnail": THUMB,
        "info": "Partite e canali da LiveSoccerTV",
    }]
    day = None
    for ev in events:
        if ev["date"] != day:
            day = ev["date"]
            d = datetime.strptime(day, "%Y-%m-%d")
            items.append({
                "title": f"[COLOR cyan]{GIORNI[d.weekday()]} {d.day} {MESI[d.month]}[/COLOR]",
                "link": "ignoreme",
                "thumbnail": THUMB,
                "info": "",
            })
        if ev["status"] == "live":
            color, tag = "red", " [COLOR red]LIVE[/COLOR]"
        elif ev["status"] == "finished":
            color, tag = "gray", (f" [COLOR gray]{ev['score']}[/COLOR]" if ev["score"] else "")
        else:
            color, tag = "yellow", ""
        names = ", ".join(c["name"] for c in ev["channels"]) or "Nessun canale indicato"
        items.append({
            "title": f"[COLOR {color}]{ev['time']}[/COLOR] {ev['title']}{tag}",
            "link": "ignoreme",
            "thumbnail": THUMB,
            "canali": [c["name"] for c in ev["channels"]],
            "info": f"{ev['competition']}\nCanali: {names}\n{ev['match_url']}",
        })
    return {"SetViewMode": "51", "items": items}


CHALLENGE_TITLES = ("just a moment", "un momento", "un attimo", "attention required", "checking your browser")
CHALLENGE_TEXT = ("verifica di sicurezza", "security verification", "verify you are human",
                  "verifica di essere umano", "just a moment", "un momento", "un attimo")


def is_challenge(page):
    """True se la pagina e' la verifica Cloudflare (titolo o testo, anche in italiano)."""
    try:
        t = (page.title() or "").lower()
        if any(k in t for k in CHALLENGE_TITLES):
            return True
        if page.query_selector('iframe[src*="challenges.cloudflare.com"]'):
            return True
        body = (page.inner_text("body", timeout=2000) or "").lower()
        return len(body) < 600 and any(k in body for k in CHALLENGE_TEXT)
    except Exception:
        return True


def cloudflare_wait(page, seconds=60):
    for _ in range(seconds):
        if not is_challenge(page):
            return True
        page.wait_for_timeout(1000)
    return False


def try_click_turnstile(page):
    """Tentativo a basso costo: clic sul riquadro della verifica, se presente."""
    try:
        frame = page.query_selector('iframe[src*="challenges.cloudflare.com"]')
        box = frame.bounding_box() if frame else None
        if box:
            page.mouse.click(box["x"] + 28, box["y"] + box["height"] / 2)
            log("Clic sul riquadro di verifica")
    except Exception:
        pass


def wait_for_rows(page, seconds=90):
    """Attende che compaiano le righe partita: e' il vero segnale che Cloudflare ha lasciato passare."""
    for i in range(seconds):
        try:
            if page.query_selector("tr.matchrow"):
                return True
        except Exception:
            pass
        if i and i % 10 == 0:
            try_click_turnstile(page)
        page.wait_for_timeout(1000)
    return False


def dump_debug(page, comp, tag):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    base = os.path.join(DEBUG_DIR, f"{comp['slug']}_{tag}")
    try:
        page.screenshot(path=base + ".png")
    except Exception:
        pass
    try:
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception:
        pass


def build_proxy_kwarg():
    """Trasforma PROXY_SERVER in {"server": ..., "username": ..., "password": ...} per
    Playwright, staccando eventuali credenziali scritte nell'indirizzo
    (http://utente:password@host:porta), che Playwright vuole separate."""
    if not PROXY_SERVER:
        return {}
    m = re.match(r"^(https?://)([^:@/]+):([^@/]+)@(.+)$", PROXY_SERVER)
    if m:
        scheme, user, pwd, rest = m.groups()
        return {"proxy": {"server": scheme + rest, "username": user, "password": pwd}}
    return {"proxy": {"server": PROXY_SERVER}}


def launch_browser(pw):
    args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    proxy_kwarg = build_proxy_kwarg()
    if proxy_kwarg:
        log(f"Proxy: {proxy_kwarg['proxy']['server']}")
    if BROWSER_CHANNEL != "chromium":
        try:
            browser = pw.chromium.launch(channel=BROWSER_CHANNEL, headless=HEADLESS, args=args, **proxy_kwarg)
            log(f"Browser: {BROWSER_CHANNEL}")
            return browser
        except Exception as e:
            log(f"Canale {BROWSER_CHANNEL} non disponibile ({str(e).splitlines()[0]}), uso Chromium")
    return pw.chromium.launch(headless=HEADLESS, args=args, **proxy_kwarg)


def new_context(browser):
    kwargs = dict(locale="it-IT", timezone_id=TARGET_TZ, viewport={"width": 1366, "height": 900})
    probe = browser.new_context()
    ua = probe.new_page().evaluate("navigator.userAgent")
    probe.close()
    if "Headless" in ua:
        kwargs["user_agent"] = ua.replace("HeadlessChrome", "Chrome")
    ctx = browser.new_context(**kwargs)
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return ctx


def warmup(ctx):
    """Visita la home una volta per ottenere il cookie Cloudflare, poi lo riusa per tutte le pagine."""
    page = ctx.new_page()
    try:
        page.goto(BASE + "/it/", wait_until="domcontentloaded", timeout=60000)
        ok = cloudflare_wait(page)
        page.wait_for_timeout(2000)
        log("Warm up home: " + ("ok" if ok else "challenge non superato"))
    except Exception as e:
        log(f"Warm up fallito: {str(e).splitlines()[0]}")
    finally:
        page.close()


def scrape_competition(ctx, comp, debug):
    page = ctx.new_page()
    try:
        url = BASE + comp["path"]
        log(f"Carico {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if not wait_for_rows(page):
            blocked = is_challenge(page)
            dump_debug(page, comp, "blocked" if blocked else "norows")
            raise RuntimeError("Cloudflare non superato (verifica di sicurezza)" if blocked
                               else "Nessuna riga partita trovata (pagina non caricata o struttura cambiata)")
        if debug:
            os.makedirs(DEBUG_DIR, exist_ok=True)
            with open(os.path.join(DEBUG_DIR, f"{comp['slug']}.html"), "w", encoding="utf-8") as f:
                f.write(page.content())
        learn_italian_channels(page)
        rows = collect_all_pages(page)
        log(f"Righe partita estratte: {len(rows)}")
        return rows
    finally:
        page.close()


# La pagina competizione mostra una decina di partite alla volta, con i pulsanti
# "Prec." e "Avanti" che caricano il resto via AJAX: senza scorrere si perdono le
# partite gia' giocate oggi e quelle dei giorni successivi.
PAGES_BACK = int(os.environ.get("PAGES_BACK", "1"))
PAGES_AHEAD = int(os.environ.get("PAGES_AHEAD", "4"))
LIST_DAYS = int(os.environ.get("LIST_DAYS", "21"))

FIRST_ROW_JS = "() => { const r = document.querySelector('tr.matchrow'); return r ? r.id : ''; }"


def turn_page(page, direction):
    """Clicca Prec./Avanti e aspetta che la tabella cambi. False se non c'e' altra pagina."""
    sel = "div.pagination-left" if direction == "previous" else "div.pagination-right"
    btn = page.query_selector(sel)
    if not btn:
        return False
    before = page.evaluate(FIRST_ROW_JS)
    last_err = ""
    for tentativo in (1, 2):
        try:
            btn = page.query_selector(sel)
            if not btn:
                return False
            btn.scroll_into_view_if_needed(timeout=5000)
            btn.click(timeout=10000)
            page.wait_for_function(
                "(b) => { const r = document.querySelector('tr.matchrow'); return r && r.id !== b; }",
                arg=before, timeout=25000)
            page.wait_for_timeout(700)
            return True
        except Exception as e:
            last_err = str(e).splitlines()[0] if str(e) else repr(e)
            page.wait_for_timeout(2000)
    log(f"  Pagina {direction} non caricata: {last_err}")
    return False


def collect_all_pages(page):
    seen, rows = set(), []

    def add(batch):
        nuove = 0
        for r in batch:
            key = r.get("id") or r.get("url")
            if key and key not in seen:
                seen.add(key)
                rows.append(r)
                nuove += 1
        return nuove

    add(page.evaluate(EXTRACT_JS))
    # indietro: partite di oggi gia' iniziate prima di quelle mostrate
    back = 0
    for _ in range(PAGES_BACK):
        if not turn_page(page, "previous"):
            break
        back += 1
        log(f"  Pagina precedente: {add(page.evaluate(EXTRACT_JS))} partite nuove")
    # avanti: si riparte dalla pagina precedente, quindi servono back giri in piu'
    limite = (datetime.now(ZoneInfo(TARGET_TZ)) + timedelta(days=LIST_DAYS)).timestamp() * 1000
    for i in range(back + PAGES_AHEAD):
        if not turn_page(page, "next"):
            break
        batch = page.evaluate(EXTRACT_JS)
        n = add(batch)
        if i >= back:
            log(f"  Pagina successiva: {n} partite nuove")
        # le prime "back" pagine riportano solo alla pagina di partenza: il controllo
        # della data vale dalla prima pagina davvero nuova in poi
        ultimi = [int(r["dv"]) for r in batch if (r.get("dv") or "").isdigit()]
        if i >= back and ultimi and min(ultimi) > limite:
            break
    return rows


def get_rows(ctx, comp, args):
    if args.html:
        page = ctx.new_page()
        with open(args.html, encoding="utf-8") as f:
            page.set_content(f.read())
        learn_italian_channels(page)
        rows = page.evaluate(EXTRACT_JS)
        page.close()
        return rows
    return scrape_competition(ctx, comp, args.debug)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true", help="salva l'HTML in debug/ e stampa i dati grezzi")
    ap.add_argument("--html", help="usa un HTML salvato invece di aprire il sito (test parser)")
    ap.add_argument("--only", help="slug di una sola competizione (es. serie-b)")
    args = ap.parse_args()

    comps = [c for c in COMPETITIONS if not args.only or c["slug"] == args.only]
    if not comps:
        sys.exit(f"Competizione sconosciuta: {args.only}")

    os.makedirs(OUT_DIR, exist_ok=True)
    now = datetime.now(ZoneInfo(TARGET_TZ))
    all_events, failures = [], 0

    with sync_playwright() as pw:
        browser = launch_browser(pw)
        ctx = new_context(browser)
        if not args.html:
            warmup(ctx)
        for n, comp in enumerate(comps):
            if n and not args.html:
                time.sleep(random.uniform(5, 10))
            rows, last_err = None, ""
            for attempt in (1, 2, 3):
                try:
                    rows = get_rows(ctx, comp, args)
                    break
                except Exception as e:
                    last_err = str(e).splitlines()[0] if str(e) else repr(e)
                    log(f"ERRORE {comp['name']} (tentativo {attempt}): {last_err}")
                    if attempt < 3:
                        ctx.close()
                        time.sleep(random.uniform(8, 15))
                        ctx = new_context(browser)
                        warmup(ctx)
            if rows is None:
                warn(f"{comp['name']} non aggiornata: {last_err}")
                failures += 1
                continue
            if args.debug:
                for r in rows[:5]:
                    log(f"  RAW: {r['dv']} | {r['timer']} | {r['title']} | {r['score']} | {[c['name'] for c in r['channels']]}")

            rows = drop_replays(rows)

            for r in rows:
                # dalla lista si tengono solo i canali italiani (vedi is_italian_channel):
                # se la pagina della partita viene letta, vengono comunque sostituiti
                r["channels"] = [c for c in r.get("channels", []) if is_italian_channel(c)]

            if comp.get("channels_from_match_page") and not args.html:
                orizzonte = now + timedelta(days=MATCH_PAGE_DAYS)
                da_controllare = [r for r in rows if r.get("url") and row_is_relevant(r, now)
                                  and (row_kickoff(r) or now) <= orizzonte]
                log(f"Canali IT dalla pagina partita: {len(da_controllare)} partite da controllare")
                for i, r in enumerate(da_controllare):
                    dati = fetch_match_channels_it(ctx, r["url"])
                    if dati and dati.get("italia"):
                        r["channels"] = [{"name": n, "url": "", "stream": False} for n in dati["italia"]]
                        if args.debug:
                            log(f"  {r['title']}: {dati['italia']}")
                    else:
                        log(f"  {r['title']}: canali IT non trovati, tengo quelli della pagina campionato")
                    if dati and dati.get("mondo"):
                        r["canali_mondo"] = dati["mondo"]
                    if i < len(da_controllare) - 1:
                        time.sleep(random.uniform(1, 2))

            events = normalize(rows, comp, now)
            if not events:
                warn(f"{comp['name']}: nessun evento utile, JSON esistente lasciato com'e'")
                failures += 1
                continue
            with open(os.path.join(OUT_DIR, f"{comp['slug']}.json"), "w", encoding="utf-8") as f:
                json.dump(build_kodi_json(comp, events), f, ensure_ascii=False, indent=2)
            all_events.extend(events)
            log(f"{comp['name']}: {len(events)} eventi")
        browser.close()

    if all_events:
        done = {e["competition"] for e in all_events}
        path = os.path.join(OUT_DIR, "all_events.json")
        old = []
        try:
            with open(path, encoding="utf-8") as f:
                old = json.load(f).get("events", [])
        except Exception:
            pass
        limit = now - timedelta(hours=12)
        keep = [e for e in old
                if e.get("competition") not in done and datetime.fromisoformat(e["kickoff"]) >= limit]
        merged = sorted(keep + all_events, key=lambda e: e["kickoff"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"events": merged}, f, ensure_ascii=False, indent=2)

        recent = now - timedelta(hours=3)
        minimal = [
            {
                "competizione": e["competition"],
                "titolo": e["title"],
                "data": e["date"],
                "ora": e["time"],
                "canali": [c["name"] for c in e["channels"]],
                "canali_mondo": e.get("canali_mondo", []),
            }
            for e in merged
            if e["status"] != "finished" and datetime.fromisoformat(e["kickoff"]) >= recent
        ]
        with open(os.path.join(OUT_DIR, "eventi.json"), "w", encoding="utf-8") as f:
            json.dump({"eventi": minimal}, f, ensure_ascii=False, indent=2)

    sys.exit(1 if failures == len(comps) else 0)


if __name__ == "__main__":
    main()
