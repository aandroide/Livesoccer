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
# Icona di un calendario a spirale, colorata: e' un'immagine vera (un file
# Twemoji preso da GitHub), non un carattere emoji nel testo, quindi la skin
# la disegna sempre, a differenza dei quadratini vuoti visti negli screenshot.
# Licenza Twemoji: CC-BY 4.0.
THUMB = "https://raw.githubusercontent.com/jdecked/twemoji/v15.0.3/assets/72x72/1f5d3.png"
FANART = "https://www.stadiotardini.it/wp-content/uploads/2016/12/mandrakata.jpg"

# Niente emoji: il font di molte skin Kodi non li disegna e restano quadratini
# vuoti (visto negli screenshot). Il resto dell'addon distingue le sezioni solo
# con [COLOR]/[B], quindi le cartelle del calendario usano lo stesso linguaggio,
# per integrarsi invece di spiccare come un difetto grafico.


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


def category_title(nome, totale, primo_livello):
    nome_mostrato = nome.upper() if primo_livello else nome
    peso = "[B]%s[/B]" % nome_mostrato if primo_livello else nome_mostrato
    return "[COLOR cyan]%s[/COLOR] [COLOR grey](%d)[/COLOR]" % (peso, totale)


def event_item(ev, now):
    """Il titolo (label) e' l'unica cosa che tutte le skin mostrano nell'elenco
    centrale; il campo "info" invece lo mostrano solo alcune, spesso in un
    pannello separato (vedi screenshot). Percio' i canali, che sono la cosa
    che si vuole vedere subito, vanno dentro il titolo stesso, su una seconda
    riga con [CR] (l'interruzione di riga che le etichette Kodi capiscono).
    Il resto (data, fonte, altri paesi) resta nel campo "info"."""
    stato = stato_evento(ev.get("inizio", ""), now)
    ora = ev.get("ora", "")
    if stato == "live":
        riga1 = "[COLOR red][B]%s[/B][/COLOR]  %s   [COLOR red][B](LIVE)[/B][/COLOR]" % (ora, ev["titolo"])
    elif stato == "finished":
        riga1 = "[COLOR grey][B]%s[/B][/COLOR]  [COLOR grey]%s[/COLOR]" % (ora, ev["titolo"])
    else:
        riga1 = "[COLOR yellow][B]%s[/B][/COLOR]  %s" % (ora, ev["titolo"])

    canali = ev.get("canali") or []
    if canali:
        nomi = ", ".join(c["nome"] for c in canali)
        riga2 = "     [COLOR khaki][B]Canali:[/B] %s[/COLOR]" % nomi
    else:
        riga2 = "     [COLOR grey][B]Canali:[/B] nessuno indicato[/COLOR]"
    titolo = riga1 + "[CR]" + riga2

    righe_info = []
    mondo = ev.get("canali_mondo") or []
    if mondo:
        righe_info.append("Altri paesi: %d" % len(mondo))
    if ev.get("data"):
        righe_info.append(ev["data"])
    if ev.get("fonte"):
        righe_info.append("Fonte: " + ev["fonte"])

    return {
        "title": titolo,
        "link": "ignoreme",
        "thumbnail": THUMB,
        "fanart": FANART,
        "info": "\n".join(righe_info),
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
        "title": "[COLOR cyan][B]{} {}/{}[/B][/COLOR]".format(giorni[d.weekday()], d.day, d.month),
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
        etichetta = category_title(nome, cart.get("totale", 0), primo_livello=True)

        if "sottocartelle" in cart:
            sub_items = []
            for sub in cart["sottocartelle"]:
                sub_slug = "%s-%s" % (cart_slug, slugify(sub["nome"]))
                sub_filename = sub_slug + ".json"
                write_json(out_dir, sub_filename, eventi_to_items(sub.get("eventi", []), now))
                sub_label = category_title(sub["nome"], sub.get("totale", 0), primo_livello=False)
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
