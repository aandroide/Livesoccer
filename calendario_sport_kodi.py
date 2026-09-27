#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Converte output/calendario_sport.json in un albero di JSON in formato MandraKodi
(quello che start.py/launcher.py sanno gia' leggere: {"SetViewMode":..,"items":[...]}).

Non serve nessun codice nuovo nell'addon: il motore che c'e' gia' interpreta da solo
un elemento con "externallink" come cartella che apre un altro JSON (jsonToItems ->
getExtData), esattamente come per le liste normali (vedi start.py). Qui produciamo
solo i file.

Struttura generata (2 livelli, come calendario_sport.json):
  root.json                  -> una voce per ogni cartella di primo livello (Oggi, Motori, Calcio...)
  <slug-cartella>.json       -> se ha sottocartelle, una voce per ognuna; se no, gli eventi
  <slug-cartella>-<slug-sub>.json -> gli eventi della sottocartella

Ogni file viene scritto sotto OUT_DIR e riferito con BASE_URL + nomefile, cosi' come
raw.githubusercontent.com viene gia' usato altrove nel progetto (es. eventi.json).

IMPORTANTE - cose che ho deciso senza un precedente da copiare (il generatore delle
cartelle live per paese non era disponibile): controllale e cambiale pure.
  - BASE_URL: da adattare a dove verranno davvero pubblicati questi file.
  - Stato LIVE/finita: calendario_sport.json non porta uno stato per evento (a
    differenza del vecchio eventi.json), quindi lo calcolo qui al momento della
    generazione confrontando "inizio" con l'ora corrente (finestra di 2 ore per
    considerarlo "in corso"). E' una foto al momento del giro, non aggiornata al
    secondo come la pagina web.
  - "Altri paesi": sulla pagina web e' un chip che si apre. Qui, per non dover
    scrivere un file a parte per ogni singola partita (sarebbero centinaia), lo
    riduco a una riga con il conteggio dei paesi nell'informazione dell'evento.
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
THUMB = "https://i.imgur.com/7wR0JXI.png"
FANART = "https://www.stadiotardini.it/wp-content/uploads/2016/12/mandrakata.jpg"

ICONS = {
    "Oggi": "\U0001F4C5", "Motori": "\U0001F3CE\uFE0F", "Calcio": "\u26BD",
    "Tennis": "\U0001F3BE", "Basket": "\U0001F3C0", "Volley": "\U0001F3D0",
    "Altri sport": "\U0001F3C5",
}


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "x"


def stato_evento(inizio_iso, now):
    """calendario_sport.json non porta uno stato per evento: lo stimo qui
    confrontando l'orario di inizio con 'now', con una finestra di 2 ore per
    considerare l'evento ancora in corso. Vedi nota nel docstring del modulo."""
    try:
        inizio = datetime.fromisoformat(inizio_iso)
    except (ValueError, TypeError):
        return "upcoming"
    if now < inizio:
        return "upcoming"
    if now <= inizio + timedelta(hours=2):
        return "live"
    return "finished"


def event_item(ev, now):
    stato = stato_evento(ev.get("inizio", ""), now)
    ora = ev.get("ora", "")
    if stato == "live":
        titolo = "[COLOR red]%s[/COLOR] %s [COLOR red]LIVE[/COLOR]" % (ora, ev["titolo"])
    elif stato == "finished":
        titolo = "[COLOR gray]%s[/COLOR] %s" % (ora, ev["titolo"])
    else:
        titolo = "[COLOR yellow]%s[/COLOR] %s" % (ora, ev["titolo"])

    canali = ev.get("canali") or []
    righe = []
    if canali:
        nomi = ", ".join(c["nome"] for c in canali)
        righe.append("Canali: " + nomi)
    else:
        righe.append("Nessun canale indicato")
    mondo = ev.get("canali_mondo") or []
    if mondo:
        righe.append("\U0001F30D Altri paesi: %d" % len(mondo))
    if ev.get("data"):
        righe.append(ev["data"])
    if ev.get("fonte"):
        righe.append("Fonte: " + ev["fonte"])

    return {
        "title": titolo,
        "link": "ignoreme",
        "thumbnail": THUMB,
        "fanart": FANART,
        "info": "\n".join(righe),
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
        "title": "[COLOR cyan]{} {}/{}[/COLOR]".format(giorni[d.weekday()], d.day, d.month),
        "link": "ignoreme",
        "thumbnail": THUMB,
        "fanart": FANART,
        "info": "",
    }


def eventi_to_items(eventi, now):
    items = []
    giorno = None
    for ev in sorted(eventi, key=lambda e: e.get("inizio", "")):
        if ev.get("data") != giorno:
            giorno = ev.get("data")
            h = day_header(giorno) if giorno else None
            if h:
                items.append(h)
        items.append(event_item(ev, now))
    return items


def write_json(out_dir, filename, items, view_mode="51"):
    path = os.path.join(out_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"SetViewMode": view_mode, "items": items}, f, ensure_ascii=False, indent=2)


def build(data, out_dir, now):
    os.makedirs(out_dir, exist_ok=True)
    root_items = []
    for cart in data["cartelle"]:
        nome = cart["nome"]
        cart_slug = slugify(nome)
        icona = ICONS.get(nome, "\U0001F3C6")
        etichetta = "%s %s (%d)" % (icona, nome, cart.get("totale", 0))

        if "sottocartelle" in cart:
            sub_items = []
            for sub in cart["sottocartelle"]:
                sub_slug = "%s-%s" % (cart_slug, slugify(sub["nome"]))
                sub_filename = sub_slug + ".json"
                write_json(out_dir, sub_filename, eventi_to_items(sub.get("eventi", []), now))
                sub_label = "%s (%d)" % (sub["nome"], sub.get("totale", 0))
                sub_items.append(folder_item(sub_label, sub_filename))
            write_json(out_dir, cart_slug + ".json", sub_items)
        else:
            write_json(out_dir, cart_slug + ".json", eventi_to_items(cart.get("eventi", []), now))

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
