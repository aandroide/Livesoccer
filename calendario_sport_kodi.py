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


# Guida programmi per canale. Tabella ricavata dalla lista "ITALY EPG" dell'addon
# (voci "epg@@slug"): toccando una voce l'addon legge la guida di quel canale e
# mostra orari e titoli. Sono informazioni sui palinsesti, nessun flusso video.
CANALI_EPG = {
    'Rai 1': 'rai-1',
    'Rai 2': 'rai-2',
    'Rai 3': 'rai-3',
    'Rete 4': 'rete4',
    'Canale 5': 'canale-5',
    'Italia 1': 'italia-uno',
    'La 7': 'la7',
    'TV 8': 'tv8',
    'Nove': 'nove',
    'Canale 20': 'canale-20',
    'Rai 4': 'rai-4',
    'Iris': 'iris',
    'Rai 5': 'rai-5',
    'Rai Movie': 'rai-movie',
    'Rai Premium': 'rai-premium',
    'Cielo': 'cielo',
    'Twenty Seven': 'mediaset-27',
    'TV 2000': 'tv2000',
    'La 7 Cinema': 'la7-cinema',
    'La 5': 'la-5',
    'Real Time': 'real-time',
    'QVC': 'qvc',
    'Food Network': 'foodnetwork',
    'Cine 34': 'cine-34',
    'Focus': 'focus',
    'Discovery': 'discovery',
    'Giallo': 'giallo',
    'Top Crime': 'topcrime',
    'Boing': 'boing',
    'K2': 'k2',
    'Rai Gulp': 'rai-gulp',
    'Rai YoYo': 'rai-yoyo',
    'Frisbee': 'frisbee',
    'Boing Plus': 'boing-plus',
    'Cartoonito': 'cartoonito',
    'Super!': 'super!',
    'Rai News 24': 'rai-news-24',
    'Italia Due': 'mediaset-italia-due',
    'Sky TG 24': 'sky-tg24',
    'TG COM 24': 'tgcom24',
    'DMax': 'dmax',
    'Rai Storia': 'rai-storia',
    'Mediaset Extra': 'mediaset-extra',
    'H&G TV': 'home-and-garden-tv',
    'Rai Scuola': 'rai-scuola',
    'Rai Sport': 'rai-sport',
    'Motor Trend': 'motor-trend',
    'Sportitalia': 'sportitalia',
    'Super Tennis': 'supertennis',
    'Alma TV': 'alma-tv',
    'Radio Italia TV': 'radioitaliatv',
    'RSI LA 1': 'rsi-la1',
    'RSI LA 2': 'rsi-la2',
    'Sky Uno': 'sky-uno-hd',
    'Sky Atlantic': 'sky-atlantic-hd',
    'Sky Serie': 'sky-serie-hd',
    'Sky Investigation': 'sky-investigation-hd',
    'Sky Crime': 'sky-crime',
    'Sky Adventure': 'sky-adventure',
    'Sky Arte': 'sky-arte-hd',
    'Sky Classica': 'sky-classica',
    'Comedy Central': 'comedy-central',
    'MTV': 'mtv',
    'Sky Sport 24': 'sky-sport-24',
    'Sky Sport Uno': 'sky-sport-uno',
    'Sky Sport Calcio': 'sky-sport-calcio',
    'Sky Sport Tennis': 'sky-sport-tennis',
    'Sky Sport Arena': 'sky-sport-arena',
    'Sky Sport Max': 'sky-sport-max',
    'Sky Sport Golf': 'sky-sport-golf',
    'Sky Sport F1': 'sky-sport-f1-hd',
    'Sky Sport Moto GP': 'sky-sport-motogp',
    'Sky Sport Basket': 'sky-sport-nba',
    'Sky Sport Legend': 'sky-sport-legend',
    'Sky Sport Mix': 'sky-sport-mix',
    'Sky Sport 4K': 'sky-sport-4k',
    'DAZN 1': 'zona-dazn',
    'DAZN 2': 'zona-dazn-2',
    'DAZN 3': 'zona-dazn-3',
    'DAZN 4': 'zona-dazn-4',
    'DAZN 5': 'zona-dazn-5',
    'EQU TV': 'equ-tv',
    'Horse TV': 'horse-tv-hd',
    'Bike': 'bike',
    'ACI Sport': 'aci-sport-tv',
    'Milan TV': 'milan-tv',
    'Inter TV': 'inter-tv-hd',
    'Caccia e Pesca': 'caccia-e-pesca',
    'Pesca e Caccia': 'pesca-e-caccia',
    'Sky Sport 251': 'sky-sport-hd-1',
    'Sky Sport 252': 'sky-sport-hd-2',
    'Sky Sport 253': 'sky-sport-hd-3',
    'Sky Sport 254': 'sky-sport-hd-4',
    'Sky Sport 255': 'sky-sport-hd-5',
    'Sky Sport 256': 'sky-sport-hd-6',
    'Sky Sport 257': 'sky-sport-hd-7',
    'Sky Sport 258': 'sky-sport-hd-8',
    'Sky Sport 259': 'sky-sport-hd-9',
    'Sky Sport 260': 'sky-sport-hd-10',
    'Sky Sport 261': 'sky-sport-hd-11',
    'Sky Sport 262': 'sky-sport-hd-12',
    'Sky Cinema Uno': 'sky-cinema-uno-hd',
    'Sky Cinema Due': 'sky-cinema-due-hd',
    'Sky Cinema Collection': 'sky-cinema-collection-hd',
    'Sky Cinema Family': 'sky-cinema-family-hd',
    'Sky Cinema Action': 'sky-cinema-action-hd',
    'Sky Cinema Suspence': 'sky-cinema-suspense-hd',
    'Sky Cinema Romance': 'sky-cinema-romance-hd',
    'Sky Cinema Drama': 'sky-cinema-drama-hd',
    'Sky Cinema Comedy': 'sky-cinema-comedy-hd',
    'Gambero Rosso': 'gambero-rosso-hd',
    'Sky Documentaries': 'sky-documentaries-hd',
    'Sky Nature': 'sky-nature-hd',
    'Discovery Channel': 'discovery-channel-hd',
    'History Channel': 'history-channel',
    'History Roma': 'history-roma',
    'Dea Kids': 'deakids',
    'Nick Jr.': 'nick-junior',
    'Nickelodeon': 'nickelodeon',
    'Cartoon Network': 'cartoon-network',
    'Boomerang': 'boomerang',
    'Dea Junior': 'dea-junior',
}

# Nomi usati dalle fonti del calendario che nella lista si chiamano diversamente.
ALIAS_CANALI = {
    "Sky Sport 1": "Sky Sport Uno",
    "DAZN Italia": "DAZN 1",
    "DAZN1": "DAZN 1",
    "TV8": "TV 8",
    "20": "Canale 20",
}


def _norm(nome):
    return re.sub(r"[^a-z0-9]", "", nome.lower())


_EPG_NORM = {_norm(k): v for k, v in CANALI_EPG.items()}
_ALIAS_NORM = {_norm(k): _norm(v) for k, v in ALIAS_CANALI.items()}


def slug_guida(nome_canale):
    """Restituisce lo slug della guida per un canale, o None se non e' in tabella
    (servizi in streaming come NOW o Paramount+ e canali esteri restano fuori)."""
    n = _norm(nome_canale)
    n = _ALIAS_NORM.get(n, n)
    return _EPG_NORM.get(n)


# La skin mostra al massimo DUE righe per voce: una terza viene tagliata (visto
# nello screenshot), quindi orario e titolo stanno insieme sulla prima riga e
# i canali sulla seconda. Per dare respiro si usa una voce spaziatrice tra un
# evento e l'altro (SPAZIATORE), non una riga vuota dentro al testo.
SPAZIATORE = True


def event_item(ev, now):
    stato = stato_evento(ev.get("inizio", ""), now)
    ora = ev.get("ora", "")
    titolo_ev = ev["titolo"]
    gap = "     "

    if stato == "live":
        riga1 = "[COLOR red][B]%s[/B][/COLOR]%s[B]%s[/B]   [COLOR red][B][LIVE][/B][/COLOR]" % (ora, gap, titolo_ev)
        colore = "khaki"
    elif stato == "finished":
        riga1 = "[COLOR grey][B]%s[/B]%s%s[/COLOR]" % (ora, gap, titolo_ev)
        colore = "grey"
    else:
        riga1 = "[COLOR yellow][B]%s[/B][/COLOR]%s[B]%s[/B]" % (ora, gap, titolo_ev)
        colore = "khaki"

    canali = ev.get("canali") or []
    rientro = "           "
    if canali:
        nomi = ", ".join(c["nome"] for c in canali)
        riga2 = "%s[COLOR %s][B]Canali:[/B] %s[/COLOR]" % (rientro, colore, nomi)
    else:
        riga2 = "%s[COLOR grey][B]Canali:[/B] nessuno indicato[/COLOR]" % rientro
    titolo = riga1 + "[CR]" + riga2

    # Il primo canale dell'evento che ha una guida rende la voce cliccabile.
    guida = None
    for c in canali:
        sl = slug_guida(c["nome"])
        if sl:
            guida = (c["nome"], sl)
            break

    righe_info = []
    if guida:
        righe_info.append("Tocca per la guida programmi di " + guida[0])
    mondo = ev.get("canali_mondo") or []
    if mondo:
        righe_info.append("Altri paesi: %d" % len(mondo))
    if ev.get("data"):
        righe_info.append(ev["data"])
    if ev.get("fonte"):
        righe_info.append("Fonte: " + ev["fonte"])

    item = {
        "title": titolo,
        "thumbnail": THUMB,
        "fanart": FANART,
        "info": "\n".join(righe_info),
    }
    if guida:
        item["myresolve"] = "epg@@" + guida[1]
    else:
        item["link"] = "ignoreme"
    return item


def spacer_item():
    return {"title": " ", "link": "ignoreme", "thumbnail": THUMB, "fanart": FANART, "info": ""}


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
        if SPAZIATORE and items and items[-1].get("_ev"):
            items.append(spacer_item())
        it = event_item(ev, now)
        it["_ev"] = True
        items.append(it)
    for it in items:
        it.pop("_ev", None)
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
