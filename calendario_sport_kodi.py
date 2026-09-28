#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Converte output/calendario_sport.json in un albero di JSON in formato MandraKodi.

Layout B (senza emoji - solo BBCode [COLOR]/[B]):
  - Voce principale  : titolo evento + riga Canali + riga "Guida TV"
  - Voce secondaria  : "Guarda in diretta" + orario + titolo evento

Struttura generata:
  root.json                        -> una voce per cartella di primo livello
  <slug-cartella>.json             -> sottocartelle oppure eventi
  <slug-cartella>-<slug-sub>.json  -> eventi della sottocartella
"""

import argparse
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE_URL = "https://raw.githubusercontent.com/aandroide/Livesoccer/master/output/kodi/"
TARGET_TZ = "Europe/Rome"

# Niente emoji: la skin Kodi non le disegna bene e compaiono quadratini vuoti.
# Le thumbnail restano vuote (stringa vuota) così la skin mostra solo il fanart.
THUMB = ""
FANART = "https://www.stadiotardini.it/wp-content/uploads/2016/12/mandrakata.jpg"


# ============================================================
# TABELLE CANALI
# ============================================================
CANALI_EPG = {
    'Rai 1': 'rai-1', 'Rai 2': 'rai-2', 'Rai 3': 'rai-3',
    'Rete 4': 'rete4', 'Canale 5': 'canale-5', 'Italia 1': 'italia-uno',
    'La 7': 'la7', 'TV 8': 'tv8', 'Nove': 'nove', 'Canale 20': 'canale-20',
    'Rai 4': 'rai-4', 'Iris': 'iris', 'Rai 5': 'rai-5',
    'Rai Movie': 'rai-movie', 'Rai Premium': 'rai-premium', 'Cielo': 'cielo',
    'Twenty Seven': 'mediaset-27', 'TV 2000': 'tv2000',
    'La 7 Cinema': 'la7-cinema', 'La 5': 'la-5',
    'Real Time': 'real-time', 'QVC': 'qvc', 'Food Network': 'foodnetwork',
    'Cine 34': 'cine-34', 'Focus': 'focus', 'Discovery': 'discovery',
    'Giallo': 'giallo', 'Top Crime': 'topcrime', 'Boing': 'boing', 'K2': 'k2',
    'Rai Gulp': 'rai-gulp', 'Rai YoYo': 'rai-yoyo', 'Frisbee': 'frisbee',
    'Boing Plus': 'boing-plus', 'Cartoonito': 'cartoonito', 'Super!': 'super!',
    'Rai News 24': 'rai-news-24', 'Italia Due': 'mediaset-italia-due',
    'Sky TG 24': 'sky-tg24', 'TG COM 24': 'tgcom24', 'DMax': 'dmax',
    'Rai Storia': 'rai-storia', 'Mediaset Extra': 'mediaset-extra',
    'H&G TV': 'home-and-garden-tv', 'Rai Scuola': 'rai-scuola',
    'Rai Sport': 'rai-sport', 'Motor Trend': 'motor-trend',
    'Sportitalia': 'sportitalia', 'Super Tennis': 'supertennis',
    'Alma TV': 'alma-tv', 'Radio Italia TV': 'radioitaliatv',
    'RSI LA 1': 'rsi-la1', 'RSI LA 2': 'rsi-la2',
    'Sky Uno': 'sky-uno-hd', 'Sky Atlantic': 'sky-atlantic-hd',
    'Sky Serie': 'sky-serie-hd', 'Sky Investigation': 'sky-investigation-hd',
    'Sky Crime': 'sky-crime', 'Sky Adventure': 'sky-adventure',
    'Sky Arte': 'sky-arte-hd', 'Sky Classica': 'sky-classica',
    'Comedy Central': 'comedy-central', 'MTV': 'mtv',
    'Sky Sport 24': 'sky-sport-24', 'Sky Sport Uno': 'sky-sport-uno',
    'Sky Sport Calcio': 'sky-sport-calcio', 'Sky Sport Tennis': 'sky-sport-tennis',
    'Sky Sport Arena': 'sky-sport-arena', 'Sky Sport Max': 'sky-sport-max',
    'Sky Sport Golf': 'sky-sport-golf', 'Sky Sport F1': 'sky-sport-f1-hd',
    'Sky Sport Moto GP': 'sky-sport-motogp', 'Sky Sport Basket': 'sky-sport-nba',
    'Sky Sport Legend': 'sky-sport-legend', 'Sky Sport Mix': 'sky-sport-mix',
    'Sky Sport 4K': 'sky-sport-4k',
    'DAZN 1': 'zona-dazn', 'DAZN 2': 'zona-dazn-2', 'DAZN 3': 'zona-dazn-3',
    'DAZN 4': 'zona-dazn-4', 'DAZN 5': 'zona-dazn-5',
    'EQU TV': 'equ-tv', 'Horse TV': 'horse-tv-hd', 'Bike': 'bike',
    'ACI Sport': 'aci-sport-tv', 'Milan TV': 'milan-tv', 'Inter TV': 'inter-tv-hd',
    'Caccia e Pesca': 'caccia-e-pesca', 'Pesca e Caccia': 'pesca-e-caccia',
    'Sky Sport 251': 'sky-sport-hd-1', 'Sky Sport 252': 'sky-sport-hd-2',
    'Sky Sport 253': 'sky-sport-hd-3', 'Sky Sport 254': 'sky-sport-hd-4',
    'Sky Sport 255': 'sky-sport-hd-5', 'Sky Sport 256': 'sky-sport-hd-6',
    'Sky Sport 257': 'sky-sport-hd-7', 'Sky Sport 258': 'sky-sport-hd-8',
    'Sky Sport 259': 'sky-sport-hd-9', 'Sky Sport 260': 'sky-sport-hd-10',
    'Sky Sport 261': 'sky-sport-hd-11', 'Sky Sport 262': 'sky-sport-hd-12',
    'Sky Cinema Uno': 'sky-cinema-uno-hd', 'Sky Cinema Due': 'sky-cinema-due-hd',
    'Sky Cinema Collection': 'sky-cinema-collection-hd',
    'Sky Cinema Family': 'sky-cinema-family-hd', 'Sky Cinema Action': 'sky-cinema-action-hd',
    'Sky Cinema Suspence': 'sky-cinema-suspense-hd',
    'Sky Cinema Romance': 'sky-cinema-romance-hd',
    'Sky Cinema Drama': 'sky-cinema-drama-hd', 'Sky Cinema Comedy': 'sky-cinema-comedy-hd',
    'Gambero Rosso': 'gambero-rosso-hd',
    'Sky Documentaries': 'sky-documentaries-hd', 'Sky Nature': 'sky-nature-hd',
    'Discovery Channel': 'discovery-channel-hd',
    'History Channel': 'history-channel', 'History Roma': 'history-roma',
    'Dea Kids': 'deakids', 'Nick Jr.': 'nick-junior', 'Nickelodeon': 'nickelodeon',
    'Cartoon Network': 'cartoon-network', 'Boomerang': 'boomerang',
    'Dea Junior': 'dea-junior',
}

CANALI_DIRETTA = {
    # DADDYCODE
    '20 Mediaset': ('daddyCode', '857'),
    'Canale 5': ('daddyCode', '853'),
    'EuroSport 1': ('daddyCode', '878'),
    'EuroSport 2': ('daddyCode', '879'),
    'Italia 1': ('daddyCode', '854'),
    'La7d': ('daddyCode', '856'),
    'La7d HD+': ('daddyCode', '856'),
    'La7': ('daddyCode', '855'),
    'Rai 1': ('daddyCode', '850'),
    'Rai 2': ('daddyCode', '851'),
    'Rai 3': ('daddyCode', '852'),
    'Rai Premium': ('daddyCode', '858'),
    'Rai Sport': ('daddyCode', '882'),
    'Sky Calcio 1 (251)': ('daddyCode', '871'),
    'Sky Calcio 2 (252)': ('daddyCode', '872'),
    'Sky Calcio 3 (253)': ('daddyCode', '873'),
    'Sky Calcio 4 (254)': ('daddyCode', '874'),
    'Sky Calcio 5 (255)': ('daddyCode', '875'),
    'Sky Calcio 6 (256)': ('daddyCode', '876'),
    'Sky Cinema Action': ('daddyCode', '861'),
    'Sky Cinema Collection': ('daddyCode', '859'),
    'Sky Cinema Comedy': ('daddyCode', '862'),
    'Sky Cinema Drama': ('daddyCode', '867'),
    'Sky Cinema Due +24': ('daddyCode', '866'),
    'Sky Cinema Family': ('daddyCode', '865'),
    'Sky Cinema Romance': ('daddyCode', '864'),
    'Sky Cinema Suspense': ('daddyCode', '868'),
    'Sky Cinema Uno +24': ('daddyCode', '863'),
    'Sky Cinema Uno': ('daddyCode', '860'),
    'Sky Serie': ('daddyCode', '880'),
    'Sky Sport 24': ('daddyCode', '869'),
    'Sky Sport Arena': ('daddyCode', '462'),
    'Sky Sport Calcio': ('daddyCode', '870'),
    'Sky Sport F1': ('daddyCode', '577'),
    'Sky Sport Football': ('daddyCode', '460'),
    'Sky Sport MotoGP': ('daddyCode', '575'),
    'Sky Sport Tennis': ('daddyCode', '576'),
    'Sky Sport UNO': ('daddyCode', '461'),
    'Sky Sports Golf': ('daddyCode', '574'),
    'Sky UNO': ('daddyCode', '881'),
    'DAZN 1': ('daddyCode', '877'),
    # SKY
    'Sky Uno': ('sky', 'skyuno'),
    'Sky Uno FHD': ('sky', 'skyuno'),
    'Sky Uno Plus': ('sky', 'skyunoplus'),
    'Sky Atlantic': ('sky', 'skyatlantic'),
    'Sky Serie FHD': ('sky', 'skyserie'),
    'Sky Collection': ('sky', 'skycollection'),
    'Sky Investigation': ('sky', 'skyinvestigation'),
    'Sky Adventure': ('sky', 'skyadventure'),
    'Sky Crime': ('sky', 'skycrime'),
    'Sky Documentaries': ('sky', 'skydocumentaries'),
    'Sky Nature': ('sky', 'skynature'),
    'Sky Arte': ('sky', 'skyarte'),
    'Sky TG 24': ('sky', 'tg24'),
    'Sky TG24': ('sky', 'tg24'),
    'TG 24': ('sky', 'tg24'),
    'TG 24 FHD': ('sky', 'tg24'),
    'Comedy Central': ('sky', 'comedycentral'),
    'MTV': ('sky', 'mtv'),
    'History Channel': ('sky', 'historychannel'),
    'History': ('sky', 'historychannel'),
}

ALIAS_CANALI = {
    "Sky Sport 1": "Sky Sport UNO",
    "Sky Sport 1 FHD": "Sky Sport UNO",
    "DAZN Italia": "DAZN 1",
    "DAZN1": "DAZN 1",
    "TV8": "TV 8",
    "20": "Canale 20",
    "La7D": "La7d",
    "TGCOM24": "TG COM 24",
    "SkyTg24": "Sky TG 24",
    "RaiSport": "Rai Sport",
    "SkySport24": "Sky Sport 24",
    "Sky Sport 24 HD": "Sky Sport 24",
    "SKY Go Italia": "Sky Sport Calcio",
    "NOW TV": "Sky Sport Calcio",
}


# ============================================================
# NORMALIZZAZIONE
# ============================================================
def _norm(nome):
    return re.sub(r"[^a-z0-9]", "", (nome or "").lower())


_EPG_NORM = {_norm(k): v for k, v in CANALI_EPG.items()}
_DIRETTA_NORM = {_norm(k): v for k, v in CANALI_DIRETTA.items()}
_ALIAS_NORM = {_norm(k): _norm(v) for k, v in ALIAS_CANALI.items()}


def _canonical(nome):
    n = _norm(nome)
    return _ALIAS_NORM.get(n, n)


def slug_guida(nome_canale):
    if not nome_canale:
        return None
    return _EPG_NORM.get(_canonical(nome_canale))


def resolve_diretta(nome_canale):
    if not nome_canale:
        return None
    c = _canonical(nome_canale)
    entry = _DIRETTA_NORM.get(c)
    if entry:
        command, value = entry
        return "{}@@{}".format(command, value)
    slug = _EPG_NORM.get(c)
    if slug:
        return "epg@@" + slug
    return None


# ============================================================
# UTILS
# ============================================================
def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "x"


def stato_evento(inizio_iso, now):
    try:
        inizio = datetime.fromisoformat(inizio_iso)
    except (ValueError, TypeError):
        return "upcoming"
    if now < inizio:
        return "upcoming"
    if now <= inizio + timedelta(hours=2):
        return "live"
    return "finished"


def category_title(nome, totale, primo_livello):
    nome_mostrato = nome.upper() if primo_livello else nome
    peso = "[B]%s[/B]" % nome_mostrato if primo_livello else nome_mostrato
    return "[COLOR cyan]%s[/COLOR] [COLOR grey](%d)[/COLOR]" % (peso, totale)


# ============================================================
# COSTRUZIONE TITOLI (LAYOUT B - solo BBCode, niente emoji)
# ============================================================
INDENT = "        "  # 8 spazi per indentare le sotto-voci


def _titolo_evento_base(ev, now):
    """Restituisce (riga1, riga2, canali, stato, colore)."""
    stato = stato_evento(ev.get("inizio", ""), now)
    ora = ev.get("ora", "")
    titolo_ev = ev["titolo"]
    gap = "     "

    if stato == "live":
        riga1 = "[COLOR red][B]%s[/B][/COLOR]%s[B]%s[/B]   [COLOR red][B][LIVE][/B][/COLOR]" % (ora, gap, titolo_ev)
        colore = "khaki"
    elif stato == "finished":
        riga1 = "[COLOR grey][B]%s[/B][/COLOR]%s%s[/COLOR]" % (ora, gap, titolo_ev)
        colore = "grey"
    else:
        riga1 = "[COLOR yellow][B]%s[/B][/COLOR]%s[B]%s[/B]" % (ora, gap, titolo_ev)
        colore = "khaki"

    canali = ev.get("canali") or []
    if canali:
        nomi = ", ".join(c["nome"] for c in canali)
        riga2 = "[COLOR %s][B]Canali:[/B] %s[/COLOR]" % (colore, nomi)
    else:
        riga2 = "[COLOR grey][B]Canali:[/B] nessuno indicato[/COLOR]"

    return riga1, riga2, canali, stato, colore


def _info_evento(ev, etichetta_tipo=None):
    righe = []
    if etichetta_tipo:
        righe.append(etichetta_tipo)
    mondo = ev.get("canali_mondo") or []
    if mondo:
        righe.append("Altri paesi: %d" % len(mondo))
    if ev.get("data"):
        righe.append(ev["data"])
    if ev.get("fonte"):
        righe.append("Fonte: " + ev["fonte"])
    return "\n".join(righe)


def event_items(ev, now):
    """
    Layout B, niente emoji. Due voci per evento:
      1) titolo evento + Canali + [ Guida TV ]
      2) [ Guarda in diretta ] + titolo evento
    """
    riga1, riga2, canali, stato, colore = _titolo_evento_base(ev, now)

    canale_epg = None
    slug_epg = None
    canale_diretta = None
    resolve_dir = None

    for c in canali:
        nome = c.get("nome", "")
        if not slug_epg:
            s = slug_guida(nome)
            if s:
                slug_epg = s
                canale_epg = nome
        if not resolve_dir:
            r = resolve_diretta(nome)
            if r:
                resolve_dir = r
                canale_diretta = nome
        if slug_epg and resolve_dir:
            break

    items = []

    # ---------- VOCE 1: guida TV ----------
    if slug_epg:
        titolo = (
            riga1 + "[CR]"
            + INDENT + riga2 + "[CR]"
            + INDENT + "[COLOR cyan][B]>> Guida TV[/B][/COLOR]"
        )
        items.append({
            "title": titolo,
            "thumbnail": THUMB,
            "fanart": FANART,
            "info": _info_evento(ev, "Apri la guida programmi di " + canale_epg),
            "myresolve": "epg@@" + slug_epg,
        })

    # ---------- VOCE 2: diretta ----------
    if resolve_dir:
        titolo_dir = (
            INDENT + "[COLOR lime][B]>> Guarda in diretta[/B][/COLOR]"
            + "[CR]" + INDENT + INDENT + riga1
        )
        items.append({
            "title": titolo_dir,
            "thumbnail": THUMB,
            "fanart": FANART,
            "info": _info_evento(ev, "Apri la diretta di " + (canale_diretta or "")),
            "myresolve": resolve_dir,
        })

    # ---------- FALLBACK ----------
    if not items:
        titolo = riga1 + "[CR]" + INDENT + riga2
        items.append({
            "title": titolo,
            "thumbnail": THUMB,
            "fanart": FANART,
            "info": _info_evento(ev, "Nessuna diretta associata"),
            "link": "ignoreme",
        })

    return items


# ============================================================
# SPAZIATORE / CARTELLE / INTESTAZIONI
# ============================================================
def spacer_item():
    return {
        "title": " ",
        "link": "ignoreme",
        "thumbnail": THUMB,
        "fanart": FANART,
        "info": "",
    }


def folder_item(titolo, filename):
    return {
        "title": titolo,
        "externallink": BASE_URL + filename,
        "thumbnail": THUMB,
        "fanart": FANART,
    }


def day_header(data_str):
    try:
        d = datetime.strptime(data_str, "%d/%m/%Y")
    except ValueError:
        return None
    giorni = ["Lunedi", "Martedi", "Mercoledi", "Giovedi", "Venerdi", "Sabato", "Domenica"]
    return {
        "title": "[COLOR cyan][B]--- {} {}/{} ---[/B][/COLOR]".format(
            giorni[d.weekday()], d.day, d.month
        ),
        "link": "ignoreme",
        "thumbnail": THUMB,
        "fanart": FANART,
        "info": "",
    }


def eventi_to_items(eventi, now):
    """
    Header giorno quando cambia la data.
    Spaziatore tra eventi diversi (non tra voci dello stesso evento).
    """
    items = []
    giorno = None

    for ev in sorted(eventi, key=lambda e: e.get("inizio", "")):
        if ev.get("data") != giorno:
            giorno = ev.get("data")
            h = day_header(giorno) if giorno else None
            if h:
                items.append(h)

        if items and items[-1].get("_ev"):
            items.append(spacer_item())

        voci = event_items(ev, now)
        for v in voci:
            v["_ev"] = True
            items.append(v)

    for it in items:
        it.pop("_ev", None)
    return items


# ============================================================
# BUILD
# ============================================================
def write_json(out_dir, filename, items, view_mode="51"):
    path = os.path.join(out_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"SetViewMode": view_mode, "items": items}, f,
                  ensure_ascii=False, indent=2)


def build(data, out_dir, now):
    os.makedirs(out_dir, exist_ok=True)
    root_items = []
    for cart in data["cartelle"]:
        nome = cart["nome"]
        cart_slug = slugify(nome)
        etichetta = category_title(nome, cart.get("totale", 0), primo_livello=True)

        if "sottocartelle" in cart:
            sub_items = []
            for sub in cart["sottocartelle"]:
                sub_slug = "%s-%s" % (cart_slug, slugify(sub["nome"]))
                sub_filename = sub_slug + ".json"
                write_json(out_dir, sub_filename,
                           eventi_to_items(sub.get("eventi", []), now))
                sub_label = category_title(sub["nome"], sub.get("totale", 0),
                                           primo_livello=False)
                sub_items.append(folder_item(sub_label, sub_filename))
            write_json(out_dir, cart_slug + ".json", sub_items)
        else:
            write_json(out_dir, cart_slug + ".json",
                       eventi_to_items(cart.get("eventi", []), now))

        root_items.append(folder_item(etichetta, cart_slug + ".json"))

    write_json(out_dir, "root.json", root_items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="output/calendario_sport.json")
    ap.add_argument("--out", default="output/kodi")
    args = ap.parse_args()
    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)
    now = datetime.now(ZoneInfo(TARGET_TZ))
    build(data, args.out, now)
    print("Generati i JSON Kodi in %s" % args.out)


if __name__ == "__main__":
    main()
