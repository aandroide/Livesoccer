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
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

BASE = "https://www.livesoccertv.com"

# Aggiungere qui altri campionati: slug, nome mostrato, path della pagina
COMPETITIONS = [
    {"slug": "serie-a", "name": "Serie A", "path": "/it/competitions/italy/serie-a/"},
    {"slug": "serie-b", "name": "Serie B", "path": "/it/competitions/italy/serie-b/"},
    {"slug": "serie-c", "name": "Serie C", "path": "/it/competitions/italy/lega-pro-1/"},
]

TARGET_TZ = "Europe/Rome"
OUT_DIR = os.environ.get("OUT_DIR", "output")
DEBUG_DIR = os.environ.get("DEBUG_DIR", "debug")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
BROWSER_CHANNEL = os.environ.get("BROWSER_CHANNEL", "chrome")

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
        stream: /live stream/i.test(t)
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


def log(msg):
    print(msg, flush=True)


def warn(msg):
    """Riga di avviso: in GitHub Actions compare come annotazione gialla nel riepilogo del run."""
    print(f"::warning::{msg}", flush=True)


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


def launch_browser(pw):
    args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    if BROWSER_CHANNEL != "chromium":
        try:
            browser = pw.chromium.launch(channel=BROWSER_CHANNEL, headless=HEADLESS, args=args)
            log(f"Browser: {BROWSER_CHANNEL}")
            return browser
        except Exception as e:
            log(f"Canale {BROWSER_CHANNEL} non disponibile ({str(e).splitlines()[0]}), uso Chromium")
    return pw.chromium.launch(headless=HEADLESS, args=args)


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
        rows = page.evaluate(EXTRACT_JS)
        log(f"Righe partita estratte: {len(rows)}")
        return rows
    finally:
        page.close()


def get_rows(ctx, comp, args):
    if args.html:
        page = ctx.new_page()
        with open(args.html, encoding="utf-8") as f:
            page.set_content(f.read())
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
            }
            for e in merged
            if e["status"] != "finished" and datetime.fromisoformat(e["kickoff"]) >= recent
        ]
        with open(os.path.join(OUT_DIR, "eventi.json"), "w", encoding="utf-8") as f:
            json.dump({"eventi": minimal}, f, ensure_ascii=False, indent=2)

    sys.exit(1 if failures == len(comps) else 0)


if __name__ == "__main__":
    main()
