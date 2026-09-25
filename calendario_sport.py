#!/usr/bin/env python3
"""
CALENDARIO SPORT per MandraKodi
Genera output/calendario_sport.json: un unico file diviso in cartelle.

  Oggi           tutti gli eventi di oggi, con [Categoria] nel titolo
  Motori         F1, MotoGP, WEC, Superbike, ... (sottocartella per campionato)
  Calcio         Serie A, B, C da LiveSoccerTV, il resto da Virgilio Sport
  Tennis         da Virgilio Sport (sottocartella per competizione)
  Basket         da Virgilio Sport
  Volley         da Virgilio Sport
  Altri sport    da Virgilio Sport (sottocartella per sport)

Fonti: calendari Google di Fuori Traiettoria, Dizzle0987/motorsport-calendar,
palinsesto TV8, Virgilio Sport guida TV, eventi.json di aandroide/Livesoccer,
EPG XMLTV facoltativi (variabile EPG_URLS).

Solo libreria standard Python 3.9+. Tutte le impostazioni sono qui sotto,
nelle sezioni CONFIG e MOTOR_CONFIG (sintassi JSON).

Variabili d'ambiente per test offline: ICS_DIR, DIZZLE_FILE, VIRGILIO_FILE,
LIVESOCCER_FILE.
"""
import datetime as dt
import gzip
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(ROOT, "output", "calendario_sport.json")


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# =====================================================================
# CONFIG: cartelle, fonti e regole di smistamento
# =====================================================================
CONFIG = json.loads(r"""
{
  "fuso": "Europe/Rome",
  "ore_indietro": 3,
  "cartella_oggi": true,
  "livesoccer": {
    "attivo": true,
    "url": "https://raw.githubusercontent.com/aandroide/Livesoccer/master/livesoccertv/output/eventi.json",
    "competizioni": [
      "Serie A",
      "Serie B",
      "Serie C"
    ]
  },
  "virgilio": {
    "attivo": true,
    "url": "https://sport.virgilio.it/guida-tv/",
    "sport_esclusi": [
      "automobilismo",
      "motociclismo",
      "superbike",
      "motogp",
      "formula 1"
    ],
    "eventi_esclusi": [
      "diretta gol"
    ]
  },
  "motorsport": {
    "attivo": true,
    "giorni_avanti": 60
  },
  "categorie": [
    {
      "nome": "Motori",
      "sport": []
    },
    {
      "nome": "Calcio",
      "sport": [
        "calcio"
      ]
    },
    {
      "nome": "Tennis",
      "sport": [
        "tennis",
        "padel"
      ]
    },
    {
      "nome": "Basket",
      "sport": [
        "basket",
        "pallacanestro"
      ]
    },
    {
      "nome": "Volley",
      "sport": [
        "pallavolo",
        "volley",
        "beach volley"
      ]
    },
    {
      "nome": "Altri sport",
      "sport": [
        "*"
      ]
    }
  ],
  "sottocartelle_per": {
    "Motori": "campionato",
    "Calcio": "competizione",
    "Tennis": "competizione",
    "Basket": "competizione",
    "Volley": "competizione",
    "Altri sport": "sport"
  }
}
""")

# =====================================================================
# MOTOR_CONFIG: calendari motorsport, canali fissi, TV8 ed EPG
# =====================================================================
MOTOR_CONFIG = json.loads(r"""
{
  "fuso": "Europe/Rome",
  "giorni_indietro": 1,
  "giorni_avanti": 400,
  "dizzle": {
    "url": "https://raw.githubusercontent.com/Dizzle0987/motorsport-calendar/main/data/events.json",
    "campionati": {
      "Formula 1": "Formula 1",
      "MotoGP": "MotoGP"
    }
  },
  "tv8": {
    "attivo": true,
    "giorni_avanti": 21,
    "finestra_differita_ore": 24
  },
  "numeri_canali": {
    "Sky Sport 1": "201",
    "Sky Sport F1": "207",
    "Sky Sport MotoGP": "208",
    "Sky Sport 4K": "213",
    "TV8": "8"
  },
  "epg": {
    "urls": [],
    "canali": [],
    "finestra_differita_ore": 24
  },
  "calendari": [
    {
      "nome": "Formula 1",
      "categoria": "4 ruote",
      "calendar_id": "7641664803fc60dfad4d5164811e25d43b0c5c9743611b369d7221d8c96c5968@group.calendar.google.com",
      "epg_keywords": [
        "formula 1",
        "f1"
      ],
      "canali": [
        {
          "nome": "Sky Sport F1",
          "numero": "207",
          "tipo": "diretta",
          "sessioni": [
            "prove",
            "sprint_quali",
            "sprint",
            "qualifiche",
            "gara"
          ]
        },
        {
          "nome": "Sky Sport 1",
          "numero": "201",
          "tipo": "diretta",
          "sessioni": [
            "prove",
            "sprint_quali",
            "sprint",
            "qualifiche",
            "gara"
          ]
        },
        {
          "nome": "Sky Sport 4K",
          "numero": "213",
          "tipo": "diretta",
          "sessioni": [
            "prove",
            "sprint_quali",
            "sprint",
            "qualifiche",
            "gara"
          ]
        },
        {
          "nome": "NOW",
          "numero": "",
          "tipo": "streaming",
          "sessioni": [
            "prove",
            "sprint_quali",
            "sprint",
            "qualifiche",
            "gara"
          ]
        },
        {
          "nome": "TV8",
          "numero": "8",
          "tipo": "differita",
          "sessioni": [
            "sprint",
            "qualifiche",
            "gara"
          ]
        }
      ],
      "tv8": true
    },
    {
      "nome": "Formula 2 e Formula 3",
      "categoria": "4 ruote",
      "calendar_id": "3cb81497ebcbbbf5a05b76ad3795598438f3da0a5aaf2778f3fac2333e1a4eb8@group.calendar.google.com",
      "epg_keywords": [
        "formula 2",
        "formula 3",
        "f2",
        "f3"
      ],
      "canali": [],
      "tv8": false
    },
    {
      "nome": "Formula E",
      "categoria": "4 ruote",
      "calendar_id": "57ee3abdb9e328151b99f58c7fa699004b96d0fd8154635a9ba3f0ff792ec5ec@group.calendar.google.com",
      "epg_keywords": [
        "formula e",
        "e-prix",
        "eprix"
      ],
      "canali": [],
      "tv8": false
    },
    {
      "nome": "Indycar",
      "categoria": "4 ruote",
      "calendar_id": "4fa1da292a3f742a9cfe54a0f4b4f995e8dcee98ce563700adc57776855a2ee1@group.calendar.google.com",
      "epg_keywords": [
        "indycar",
        "indy"
      ],
      "canali": [],
      "tv8": false
    },
    {
      "nome": "WEC",
      "categoria": "GT e Endurance",
      "calendar_id": "5834fcac722bcb9538c7d1aea0fce19c830c37bb000cad69a9cb99c8d47426bc@group.calendar.google.com",
      "epg_keywords": [
        "wec",
        "endurance",
        "hypercar",
        "le mans"
      ],
      "canali": [],
      "tv8": false
    },
    {
      "nome": "GT World Challenge Europe",
      "categoria": "GT e Endurance",
      "calendar_id": "8f77a59a0fc2042450eb6b3c960b5f98542d8b189c5b216739db0cf136ba27b8@group.calendar.google.com",
      "epg_keywords": [
        "gt world challenge",
        "gtwc",
        "fanatec"
      ],
      "canali": [],
      "tv8": false
    },
    {
      "nome": "MotoGP",
      "categoria": "2 ruote",
      "calendar_id": "07743cc0ced8c0709941fc143b6a25f8bc973a18af388da439489881fa379b99@group.calendar.google.com",
      "epg_keywords": [
        "motogp"
      ],
      "canali": [
        {
          "nome": "Sky Sport MotoGP",
          "numero": "208",
          "tipo": "diretta",
          "sessioni": [
            "prove",
            "sprint_quali",
            "sprint",
            "qualifiche",
            "gara"
          ]
        },
        {
          "nome": "NOW",
          "numero": "",
          "tipo": "streaming",
          "sessioni": [
            "prove",
            "sprint_quali",
            "sprint",
            "qualifiche",
            "gara"
          ]
        },
        {
          "nome": "TV8",
          "numero": "8",
          "tipo": "differita",
          "sessioni": [
            "sprint",
            "gara"
          ]
        }
      ],
      "tv8": true
    },
    {
      "nome": "Moto2 e Moto3",
      "categoria": "2 ruote",
      "calendar_id": "2aa1544514164a395c938a3a3ac5f7cc1b68ad18396448ac16a094bec9adc2cf@group.calendar.google.com",
      "epg_keywords": [
        "moto2",
        "moto3"
      ],
      "tv8_richiedi_keyword": true,
      "canali": [],
      "tv8": true
    },
    {
      "nome": "World Superbike",
      "categoria": "2 ruote",
      "calendar_id": "22bbf853f39afde51d88e9b50bba2bb8afe37e3c9de62217a03765149e2b79cb@group.calendar.google.com",
      "epg_keywords": [
        "superbike",
        "worldsbk",
        "wsbk",
        "sbk"
      ],
      "canali": [],
      "tv8": true
    },
    {
      "nome": "Special Events",
      "categoria": "Speciali",
      "calendar_id": "fff7915d9a42cba09d67004a039c3817318ed7554ddec78976d4da81cb490e65@group.calendar.google.com",
      "epg_keywords": [
        "le mans",
        "indianapolis",
        "indy 500",
        "macau",
        "macao",
        "suzuka"
      ],
      "canali": [],
      "tv8": false
    }
  ]
}
""")


# =====================================================================
# MOTORSPORT
# =====================================================================
FT_PAGE = ("https://www.fuoritraiettoria.com/4-ruote/"
           "calendari-motorsport-campionati-stagione-2026-sincronizzabili-2/")
DIZZLE_PAGE = "https://github.com/Dizzle0987/motorsport-calendar"
TV8_API = "https://www.tv8.it/api/programmingCarousel"
TV8_GUIDE = "https://www.tv8.it/programmazione"
UA = "Mozilla/5.0 (X11; Linux x86_64) calendario-sport"

# Ordine importante: i casi piu' specifici prima
SESSION_RULES = [
    ("sprint_quali", r"sprint\s*(quali\w*|shootout)"),
    ("prove", r"\b(fp\s?\d|practice|libere|prove|warm\s?up|test\w*)\b"),
    ("sprint", r"\bsprint\b"),
    ("qualifiche", r"\b(quali\w*|q[12]|superpole|pole|hyperpole)\b"),
    ("gara", r"\b(race|gara|feature|grand prix|gran premio|e-?prix|\d+\s?(ore|hours|h)\b|500)"),
]

# Sessioni che TV8 trasmette (mai le libere)
TV8_SESSIONS = {"sprint_quali", "sprint", "qualifiche", "gara"}
TV8_EXCLUDED = ("paddock", "podio", "grid", "zona rossa", "pre gara", "post gara",
                "pre-gara", "post-gara", "highlights", "magazine")

# Parole per riconoscere la sessione nei titoli TV (EPG e TV8)
TV_SESSION_WORDS = {
    "prove": ["libere", "prove", "practice", "fp1", "fp2", "fp3"],
    "sprint_quali": ["qualifiche sprint", "sprint qualifying", "sprint shootout"],
    "sprint": ["sprint"],
    "qualifiche": ["qualifiche", "qualifying", "superpole", "hyperpole"],
    "gara": ["gara", "race", "e-prix"],
    "evento": [],
}

# Nomi inglesi dei calendari e nomi italiani usati da TV8 e Sky
GP_ALIASES = {
    "dutch": "olanda", "netherlands": "olanda", "italian": "italia", "italy": "italia",
    "british": "gran bretagna", "great britain": "gran bretagna", "silverstone": "gran bretagna",
    "hungarian": "ungheria", "hungary": "ungheria", "spanish": "spagna", "spain": "spagna",
    "barcelona": "barcellona", "catalunya": "catalogna", "madrid": "madrid",
    "austrian": "austria", "german": "germania", "germany": "germania",
    "czech": "repubblica ceca", "japanese": "giappone", "japan": "giappone",
    "chinese": "cina", "china": "cina", "mexico": "messico", "mexican": "messico",
    "brazil": "brasile", "brazilian": "brasile", "portuguese": "portogallo",
    "portugal": "portogallo", "malaysian": "malesia", "malaysia": "malesia",
    "australian": "australia", "belgian": "belgio", "belgium": "belgio",
    "french": "francia", "france": "francia", "canadian": "canada",
    "singapore": "singapore", "qatar": "qatar", "saudi": "arabia saudita",
    "united states": "stati uniti", "americas": "americhe", "thai": "thailandia",
    "thailand": "thailandia", "argentina": "argentina", "aragon": "aragona",
    "valencia": "valencia", "misano": "misano", "mugello": "mugello",
    "emilia": "emilia romagna", "imola": "imola", "monaco": "monaco",
    "azerbaijan": "azerbaijan", "abu dhabi": "abu dhabi", "las vegas": "las vegas",
    "miami": "miami", "bahrain": "bahrain", "indonesian": "indonesia",
}
GP_STOPWORDS = {"gp", "grand", "prix", "gran", "premio", "di", "del", "della", "dell",
                "de", "the", "of", "round", "circuit", "circuito", "international",
                "eprix", "e-prix", "race", "city", "2025", "2026", "2027", "2028"}


def fetch(url, timeout=90, headers=None):
    hdr = {"User-Agent": UA}
    hdr.update(headers or {})
    req = urllib.request.Request(url, headers=hdr)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


def norm(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def has_word(text, word):
    word = norm(word)
    return bool(word) and re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(word), text) is not None


def session_type(label):
    low = label.lower()
    for name, rule in SESSION_RULES:
        if re.search(rule, low):
            return name
    return "evento"


def gp_terms(*parts):
    """Parole utili a riconoscere il GP nei titoli TV, con alias italiani."""
    text = norm(" ".join(p for p in parts if p))
    terms = {t for t in text.split() if len(t) > 3 and t not in GP_STOPWORDS}
    for src, dst in GP_ALIASES.items():
        if has_word(text, src):
            terms.add(norm(dst))
    return terms


# ---------------------------------------------------------------- ICS

def ics_url(cal_id):
    return ("https://calendar.google.com/calendar/ical/%s/public/basic.ics"
            % urllib.parse.quote(cal_id, safe=""))


def ics_unescape(value):
    return (value.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",")
            .replace("\\;", ";").replace("\\\\", "\\").strip())


def ics_parse_dt(value, params, default_tz):
    value = value.strip()
    if "VALUE=DATE" in params or len(value) == 8:
        day = dt.datetime.strptime(value[:8], "%Y%m%d")
        return day.replace(tzinfo=default_tz), True
    if value.endswith("Z"):
        naive = dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ")
        return naive.replace(tzinfo=dt.timezone.utc), False
    tz = default_tz
    match = re.search(r"TZID=([^;:]+)", params)
    if match:
        try:
            tz = ZoneInfo(match.group(1))
        except Exception:
            pass
    return dt.datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=tz), False


def parse_ics(text, default_tz):
    text = re.sub(r"\r?\n[ \t]", "", text)
    events, cur = [], None
    for line in text.splitlines():
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            if cur and "start" in cur and cur.get("status") != "CANCELLED":
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, value = line.split(":", 1)
            name, _, params = key.partition(";")
            if name == "SUMMARY":
                cur["title"] = ics_unescape(value)
            elif name == "LOCATION":
                cur["location"] = ics_unescape(value)
            elif name == "UID":
                cur["uid"] = value.strip()
            elif name == "STATUS":
                cur["status"] = value.strip().upper()
            elif name == "DTSTART":
                cur["start"], cur["all_day"] = ics_parse_dt(value, params, default_tz)
            elif name == "DTEND":
                cur["end"], _ = ics_parse_dt(value, params, default_tz)
    return events


def load_ics_calendar(cal, tz):
    local_dir = os.environ.get("ICS_DIR")
    if local_dir:
        path = os.path.join(local_dir, cal["calendar_id"] + ".ics")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return parse_ics(fh.read(), tz)
    return parse_ics(fetch(ics_url(cal["calendar_id"])).decode("utf-8", "replace"), tz)


def split_title(title):
    """'Azerbaijan GP - FP1' restituisce ('Azerbaijan GP', 'FP1')."""
    parts = re.split(r"\s+[-\u2013\u2014|]\s+", title, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return title.strip(), ""


def events_from_ics(cal, tz):
    out = []
    for ev in load_ics_calendar(cal, tz):
        title = ev.get("title", "")
        gp, label = split_title(title)
        start = ev["start"].astimezone(tz)
        out.append({
            "titolo": title, "gp": gp, "sessione_label": label or title,
            "start": start, "end": ev.get("end", ev["start"]).astimezone(tz),
            "all_day": ev.get("all_day", False), "circuito": ev.get("location", ""),
            "uid": ev.get("uid", ""), "stato": "", "fonte_orari": "Fuori Traiettoria",
            "terms": gp_terms(gp, ev.get("location", "")), "canali_base": [],
        })
    return out


# ---------------------------------------------------------------- DIZZLE

def parse_iso(value, tz):
    value = (value or "").strip()
    if not value:
        return None, False
    if len(value) == 10:
        return dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=tz), True
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz), False


def load_dizzle(cfg, tz, numbers):
    """Restituisce {nome_calendario: [eventi]} per i campionati mappati."""
    mapping = cfg.get("campionati", {})
    if not cfg.get("url") or not mapping:
        return {}
    local = os.environ.get("DIZZLE_FILE")
    try:
        if local and os.path.exists(local):
            with open(local, encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = json.loads(fetch(cfg["url"]).decode("utf-8"))
    except Exception as exc:
        log("Dizzle non disponibile, uso Fuori Traiettoria: %s" % exc)
        return {}
    result = {}
    for e in data.get("events", []):
        cal_name = mapping.get(e.get("competition"))
        if not cal_name or e.get("enabled") is False:
            continue
        if (e.get("status") or "").lower() in ("cancellata", "rinviata"):
            continue
        start, all_day = parse_iso(e.get("start"), tz)
        if start is None:
            continue
        end, _ = parse_iso(e.get("end"), tz)
        gp = re.sub(r"\s*\b20\d\d\b", "", e.get("grand_prix", "")).strip()
        session = e.get("session", "")
        base = []
        broadcaster = (e.get("broadcaster_it") or "").strip()
        if broadcaster:
            tipo = e.get("broadcast_type_it") or "diretta"
            match = re.search(r"(\d{1,2}):(\d{2})", e.get("broadcast_time_it") or "")
            # l'orario di messa in onda serve solo per la differita: per la diretta
            # vale l'orario della sessione (quello di Dizzle a volte e' vecchio, es. cambio ora)
            if tipo == "differita" and match:
                when = start.replace(hour=int(match.group(1)), minute=int(match.group(2)))
            else:
                when = start
            for name in [n.strip() for n in broadcaster.split("/") if n.strip()]:
                base.append({"nome": name, "numero": numbers.get(name, ""),
                             "tipo": "streaming" if name.upper() == "NOW" else tipo,
                             "orario": when.strftime("%Y-%m-%dT%H:%M"),
                             "fonte": "dizzle"})
        circuito = ", ".join(p for p in (e.get("circuit"), e.get("location"), e.get("country")) if p)
        result.setdefault(cal_name, []).append({
            "titolo": "%s - %s" % (gp, session), "gp": gp, "sessione_label": session,
            "start": start, "end": end or start + dt.timedelta(hours=1),
            "all_day": all_day, "circuito": circuito, "uid": e.get("uid", ""),
            "stato": e.get("status", ""), "fonte_orari": "Dizzle0987/motorsport-calendar",
            "terms": gp_terms(gp, e.get("circuit"), e.get("location"), e.get("country")),
            "canali_base": base,
        })
    for name, evs in result.items():
        log("Dizzle %s: %d eventi" % (name, len(evs)))
    return result


# ---------------------------------------------------------------- TV8

def tv8_day(day, tz, cache):
    key = day.isoformat()
    if key in cache:
        return cache[key]
    start = dt.datetime.combine(day, dt.time.min, tz).astimezone(dt.timezone.utc)
    end = dt.datetime.combine(day, dt.time.max, tz).astimezone(dt.timezone.utc)
    fmt = lambda d: d.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    url = "%s?%s" % (TV8_API, urllib.parse.urlencode({"from": fmt(start), "to": fmt(end)}))
    programs = []
    try:
        payload = json.loads(fetch(url, timeout=30, headers={"Referer": TV8_GUIDE}).decode("utf-8"))
        for prog in payload.get("programs", []):
            title = str((prog.get("title") or {}).get("text", ""))
            desc = str((prog.get("description") or {}).get("text", ""))
            label = str(((prog.get("badge") or {}).get("label") or {}).get("text", ""))
            match = re.match(r"^(\d{2}):(\d{2})\s*-\s*(\d{2}):(\d{2})$", label.strip())
            if not match:
                continue
            sh, sm, eh, em = map(int, match.groups())
            p_start = dt.datetime.combine(day, dt.time(sh, sm), tz)
            p_end = dt.datetime.combine(day, dt.time(eh, em), tz)
            if p_end <= p_start:
                p_end += dt.timedelta(days=1)
            programs.append({"titolo": title, "testo": norm(title + " " + desc),
                             "titolo_norm": norm(title), "start": p_start, "stop": p_end})
    except Exception as exc:
        log("TV8 %s non disponibile: %s" % (key, exc))
    cache[key] = programs
    return programs


def tv8_matches(ev, sess, cal, other_keywords, tz, cache, max_delay_h):
    if sess not in TV8_SESSIONS or ev["all_day"]:
        return []
    start = ev["start"]
    days = {start.date(), (start + dt.timedelta(hours=max_delay_h)).date()}
    words = TV_SESSION_WORDS.get(sess, [])
    own = [norm(k) for k in cal.get("epg_keywords", [])]
    found = []
    for day in sorted(days):
        for prog in tv8_day(day, tz, cache):
            title = prog["titolo_norm"]
            if any(x in title for x in TV8_EXCLUDED):
                continue
            if sess == "sprint" and "qualif" in title:
                continue
            if sess == "qualifiche" and "sprint" in title:
                continue
            if sess == "gara" and "sprint" in title:
                continue
            if not any(has_word(title, w) for w in words):
                continue
            # Superbike: "Race 2" deve trovare "Gara 2", "SP Race" solo "Superpole Race"
            label = norm(ev.get("sessione_label", ""))
            is_sp = "superpole race" in label or re.search(r"\bsp race\b", label) is not None
            if is_sp != ("superpole" in title and ("race" in title or "gara" in title)) and sess == "gara":
                continue
            num = re.search(r"\b(?:race|gara)\s*(\d)\b", label)
            if num and not re.search(r"\b(?:race|gara)\s*%s\b" % num.group(1), title):
                continue
            if ev["terms"] and not any(has_word(prog["testo"], t) for t in ev["terms"]):
                continue
            # evita di attribuire alla F1 un programma MotoGP dello stesso GP
            mentions_own = any(has_word(prog["testo"], k) for k in own)
            if not mentions_own and any(has_word(prog["testo"], k) for k in other_keywords):
                continue
            # per le classi minori (Moto2/Moto3) il programma deve nominarle, altrimenti
            # si rischia di prendere la gara della MotoGP dello stesso weekend
            if cal.get("tv8_richiedi_keyword") and not mentions_own:
                continue
            delta = (prog["start"] - start).total_seconds() / 60
            if -90 <= delta <= 10 and prog["stop"] >= start:
                tipo = "diretta"
            elif 10 < delta <= max_delay_h * 60:
                tipo = "differita"
            else:
                continue
            found.append({"nome": "TV8", "numero": "8", "tipo": tipo,
                          "orario": prog["start"].strftime("%Y-%m-%dT%H:%M"),
                          "programma": prog["titolo"], "fonte": "tv8"})
    if not found:
        return []
    live = [f for f in found if f["tipo"] == "diretta"]
    return [min(live or found, key=lambda f: f["orario"])]


# ---------------------------------------------------------------- EPG XMLTV

def parse_xmltv_time(value):
    value = value.strip()
    base = dt.datetime.strptime(value[:14], "%Y%m%d%H%M%S")
    match = re.search(r"([+-])(\d{2})(\d{2})$", value)
    if match:
        sign = 1 if match.group(1) == "+" else -1
        offset = dt.timedelta(hours=int(match.group(2)), minutes=int(match.group(3)))
        return base.replace(tzinfo=dt.timezone(sign * offset))
    return base.replace(tzinfo=dt.timezone.utc)


def load_epg(urls, wanted_channels):
    wanted = {c.lower() for c in wanted_channels}
    names, programmes = {}, []
    for url in urls:
        try:
            root = ET.fromstring(fetch(url, timeout=180))
        except Exception as exc:
            log("EPG non utilizzabile %s: %s" % (url, exc))
            continue
        for ch in root.iter("channel"):
            names[ch.get("id")] = (ch.findtext("display-name") or ch.get("id")).strip()
        count = 0
        for prog in root.iter("programme"):
            ch_id = prog.get("channel", "")
            disp = names.get(ch_id, ch_id)
            if wanted and ch_id.lower() not in wanted and disp.lower() not in wanted:
                continue
            try:
                p_start = parse_xmltv_time(prog.get("start"))
                p_stop = parse_xmltv_time(prog.get("stop") or prog.get("start"))
            except (TypeError, ValueError):
                continue
            title = (prog.findtext("title") or "").strip()
            text = norm(" ".join(filter(None, [title, prog.findtext("sub-title"), prog.findtext("desc")])))
            programmes.append({"canale": disp, "start": p_start, "stop": p_stop,
                               "titolo": title, "testo": text})
            count += 1
        log("EPG %s: %d programmi" % (url, count))
    return programmes


def epg_matches(ev, sess, cal, programmes, tz, max_delay_h):
    if not programmes or ev["all_day"]:
        return []
    keywords = cal.get("epg_keywords", [])
    words = TV_SESSION_WORDS.get(sess, [])
    start = ev["start"]
    best = {}
    for prog in programmes:
        text = prog["testo"]
        if not any(has_word(text, k) for k in keywords):
            continue
        delta = (prog["start"] - start).total_seconds() / 60
        if -90 <= delta <= 20 and prog["stop"] > start:
            tipo = "diretta"
        elif 20 < delta <= max_delay_h * 60:
            if words and not any(has_word(text, w) for w in words):
                continue
            if ev["terms"] and not any(has_word(text, t) for t in ev["terms"]):
                continue
            tipo = "differita"
        else:
            continue
        item = {"nome": prog["canale"], "numero": "", "tipo": tipo,
                "orario": prog["start"].astimezone(tz).strftime("%Y-%m-%dT%H:%M"),
                "programma": prog["titolo"], "fonte": "epg"}
        key = (norm(item["nome"]), tipo)
        if key not in best or item["orario"] < best[key]["orario"]:
            best[key] = item
    return list(best.values())


# ---------------------------------------------------------------- MERGE

def same_channel(a, b):
    na, nb = norm(a), norm(b)
    return na == nb or (len(na) > 3 and len(nb) > 3 and (na in nb or nb in na))


def add_channel(channels, new):
    """Aggiunge un canale evitando doppioni; una diretta vince sulla differita."""
    for cur in channels:
        if not same_channel(cur["nome"], new["nome"]):
            continue
        if cur["tipo"] == new["tipo"] or cur["tipo"] == "streaming":
            if new.get("orario") and new["fonte"] in ("tv8", "epg"):
                cur["orario"] = new["orario"]
            if new["fonte"] not in cur["fonte"]:
                cur["fonte"] += "+" + new["fonte"]
            return
        if cur["tipo"] == "diretta":
            return  # c'e' gia' la diretta: la differita non serve
        if new["tipo"] == "diretta" and new["fonte"] in ("tv8", "epg", "dizzle"):
            cur.update(new)  # la differita prevista e' in realta' una diretta
            return
    channels.append(dict(new))


def build_motorsport(cfg):
    tz = ZoneInfo(cfg.get("fuso", "Europe/Rome"))
    now = dt.datetime.now(tz)
    since = now - dt.timedelta(days=cfg.get("giorni_indietro", 1))
    until = now + dt.timedelta(days=cfg.get("giorni_avanti", 400))
    numbers = cfg.get("numeri_canali", {})

    dizzle = load_dizzle(cfg.get("dizzle", {}), tz, numbers)

    epg_cfg = cfg.get("epg", {})
    env_urls = [u.strip() for u in os.environ.get("EPG_URLS", "").split(",") if u.strip()]
    programmes = load_epg(env_urls or epg_cfg.get("urls", []), epg_cfg.get("canali", []))
    epg_delay = epg_cfg.get("finestra_differita_ore", 24)

    tv8_cfg = cfg.get("tv8", {})
    tv8_on = tv8_cfg.get("attivo", True)
    tv8_until = now + dt.timedelta(days=tv8_cfg.get("giorni_avanti", 21))
    tv8_delay = tv8_cfg.get("finestra_differita_ore", 24)
    tv8_cache = {}
    all_keywords = {c["nome"]: [norm(k) for k in c.get("epg_keywords", [])] for c in cfg["calendari"]}

    eventi, errori, fonti = [], [], {}
    for cal in cfg["calendari"]:
        name = cal["nome"]
        if dizzle.get(name):
            raw, fonti[name] = dizzle[name], "Dizzle0987/motorsport-calendar"
        else:
            try:
                raw, fonti[name] = events_from_ics(cal, tz), "Fuori Traiettoria"
                log("%s: %d eventi da Fuori Traiettoria" % (name, len(raw)))
            except Exception as exc:
                log("Calendario %s non scaricato: %s" % (name, exc))
                errori.append(name)
                continue
        others = [k for n, ks in all_keywords.items() if n != name for k in ks
                  if k not in all_keywords.get(name, [])]
        for ev in raw:
            start = ev["start"]
            if not (since <= start <= until):
                continue
            sess = session_type(ev["sessione_label"])
            channels = []
            for c in ev["canali_base"]:
                add_channel(channels, c)
            for c in cal.get("canali", []):
                if c.get("sessioni") and sess not in c["sessioni"]:
                    continue
                add_channel(channels, {
                    "nome": c["nome"], "numero": c.get("numero") or numbers.get(c["nome"], ""),
                    "tipo": c["tipo"],
                    "orario": "" if c["tipo"] == "differita" else start.strftime("%Y-%m-%dT%H:%M"),
                    "fonte": "config"})
            if tv8_on and cal.get("tv8") and start <= tv8_until:
                for c in tv8_matches(ev, sess, cal, others, tz, tv8_cache, tv8_delay):
                    add_channel(channels, c)
            for c in epg_matches(ev, sess, cal, programmes, tz, epg_delay):
                add_channel(channels, c)
            for c in channels:
                c["numero"] = c.get("numero") or numbers.get(c["nome"], "")
            eventi.append({
                "campionato": name,
                "categoria": cal["categoria"],
                "titolo": ev["titolo"],
                "gp": ev["gp"],
                "sessione": sess,
                "sessione_label": ev["sessione_label"],
                "inizio": start.isoformat(),
                "fine": ev["end"].isoformat(),
                "data": start.strftime("%d/%m/%Y"),
                "ora": "" if ev["all_day"] else start.strftime("%H:%M"),
                "tutto_il_giorno": ev["all_day"],
                "circuito": ev["circuito"],
                "stato": ev["stato"],
                "fonte_orari": ev["fonte_orari"],
                "uid": ev["uid"],
                "canali": channels,
            })

    eventi.sort(key=lambda e: (e["inizio"], e["campionato"]))
    return {
        "aggiornato": now.isoformat(timespec="seconds"),
        "fonti": {"fuori_traiettoria": FT_PAGE, "dizzle": DIZZLE_PAGE, "tv8": TV8_GUIDE},
        "fonte_per_campionato": fonti,
        "calendari_non_scaricati": errori,
        "totale": len(eventi),
        "eventi": eventi,
    }

# =====================================================================
# VIRGILIO SPORT, GUIDA TV
# =====================================================================
VIRGILIO_URL = "https://sport.virgilio.it/guida-tv/"
VIRGILIO_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
MONTHS = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
          "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10,
          "novembre": 11, "dicembre": 12}
DATE_RE = re.compile(r"\b(\d{1,2})\s+(%s)\s+(20\d\d)\b" % "|".join(MONTHS), re.I)
TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s*$")
CHANNEL_FIX = {"dazn": "DAZN", "rai sport": "Rai Sport", "tv8": "TV8", "now": "NOW"}


class _Collector(HTMLParser):
    """Raccoglie in ordine di pagina i testi fuori tabella e le righe delle tabelle."""

    BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "p", "caption", "strong", "b", "div", "span", "li"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []          # ("text", str) oppure ("row", [celle])
        self.row = None
        self.cell = None
        self.text = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        elif tag == "tr":
            self._flush_text()
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag == "br":
            (self.cell if self.cell is not None else self.text).append(" | ")
        elif tag in self.BLOCK_TAGS and self.cell is None:
            self._flush_text()

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        elif tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(_clean("".join(self.cell)))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if any(self.row):
                self.items.append(("row", self.row))
            self.row = None
        elif tag in self.BLOCK_TAGS and self.cell is None:
            self._flush_text()

    def handle_data(self, data):
        if self.skip:
            return
        if self.cell is not None:
            self.cell.append(data)
        elif self.row is None:
            self.text.append(data)

    def _flush_text(self):
        txt = _clean("".join(self.text))
        if txt:
            self.items.append(("text", txt))
        self.text = []

    def close(self):
        super().close()
        self._flush_text()


def _clean(text):
    return re.sub(r"\s+", " ", text).strip()


def _channels(text):
    out = []
    for part in re.split(r",|\s\|\s|/", text):
        name = _clean(part.strip(" |"))
        if not name:
            continue
        name = CHANNEL_FIX.get(name.lower(), name)
        if name not in out:
            out.append(name)
    return out


def _split_event(text):
    """'Basket, NBA: | Oklahoma City-Minnesota' diventa (Basket, NBA, Oklahoma City-Minnesota)."""
    text = _clean(text.replace(" | ", " "))
    head, sep, event = text.partition(":")
    if not sep:
        head, event = text, ""
    sport, _, comp = head.partition(",")
    return _clean(sport), _clean(comp), _clean(event) or _clean(comp) or _clean(sport)


def parse_virgilio(html, tz):
    col = _Collector()
    col.feed(html)
    col.close()
    events, day = [], None
    for kind, value in col.items:
        cells = value if kind == "row" else [value]
        joined = " ".join(cells)
        # intestazione del giorno: testo libero o riga di tabella senza orario
        if not (kind == "row" and len(cells) >= 3 and TIME_RE.match(cells[0])):
            match = DATE_RE.search(joined)
            if match:
                day = dt.date(int(match.group(3)), MONTHS[match.group(2).lower()], int(match.group(1)))
            continue
        if day is None:
            continue
        hh, mm = TIME_RE.match(cells[0]).groups()
        start = dt.datetime.combine(day, dt.time(int(hh), int(mm)), tz)
        sport, comp, event = _split_event(cells[1])
        channels = _channels(cells[2])
        if not channels:
            continue
        events.append({"sport": sport, "competizione": comp, "evento": event,
                       "start": start, "canali": channels})
    # via i doppioni esatti (stessa ora, evento e canali)
    seen, unique = set(), []
    for ev in events:
        key = (ev["start"], ev["sport"].lower(), ev["evento"].lower(), tuple(ev["canali"]))
        if key not in seen:
            seen.add(key)
            unique.append(ev)
    return unique


def load_virgilio(url=VIRGILIO_URL, tz=None):
    tz = tz or ZoneInfo("Europe/Rome")
    local = os.environ.get("VIRGILIO_FILE")
    if local and os.path.exists(local):
        with open(local, encoding="utf-8") as fh:
            html = fh.read()
    else:
        req = urllib.request.Request(url, headers={"User-Agent": VIRGILIO_UA, "Accept-Language": "it-IT,it"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            html = resp.read().decode("utf-8", "replace")
    events = parse_virgilio(html, tz)
    log("Virgilio: %d eventi" % len(events))
    return events

# =====================================================================
# CALENDARIO UNICO: LIVESOCCER, SMISTAMENTO E CARTELLE
# =====================================================================
def folder_name(text):
    """Toglie le stagioni dai nomi cartella: 'Eurolega 2026-2027' diventa 'Eurolega'."""
    text = re.sub(r"\b20\d\d(\s*[-/]\s*(20)?\d\d)?\b", "", text or "")
    return re.sub(r"\s{2,}", " ", text).strip(" ,.-") or "Varie"


def pick_category(sport, categories):
    low = sport.lower()
    for cat in categories:
        keys = cat.get("sport", [])
        if "*" in keys or not keys:
            continue
        if any(low == k or low.startswith(k + " ") or low.startswith(k + ",") for k in keys):
            return cat["nome"]
    fallback = next((c["nome"] for c in categories if "*" in c.get("sport", [])), "Altri sport")
    return fallback


def motor_events(cfg, tz, now):
    if not cfg.get("attivo", True):
        return []
    try:
        data = build_motorsport(MOTOR_CONFIG)
    except Exception as exc:
        log("Motorsport non disponibile: %s" % exc)
        return []
    order = [c["nome"] for c in MOTOR_CONFIG["calendari"]]
    until = now + dt.timedelta(days=cfg.get("giorni_avanti", 60))
    out = []
    for e in data["eventi"]:
        start = dt.datetime.fromisoformat(e["inizio"]).astimezone(tz)
        if start > until:
            continue
        out.append({
            "titolo": "%s: %s" % (e["campionato"], e["titolo"]),
            "categoria": "Motori",
            "sottocartella": e["campionato"],
            "_ordine_sottocartella": order.index(e["campionato"]) if e["campionato"] in order else 99,
            "sport": "Motori",
            "competizione": e["campionato"],
            "evento": e["titolo"],
            "sessione": e["sessione"],
            "circuito": e["circuito"],
            "inizio": start.isoformat(),
            "data": e["data"],
            "ora": e["ora"],
            "canali": e["canali"],
            "fonte": e["fonte_orari"],
        })
    return out


def merge_virgilio(events):
    """Unisce le righe di Virgilio che sono lo stesso evento:
    - stessa gara passata da un canale all'altro (ciclismo: Eurosport, poi Rai Sport,
      poi Rai 2) diventa un evento solo, con l'orario di ogni canale;
    - una riga generica ("Laver Cup") alla stessa ora di una specifica
      ("Laver Cup: 1a Giornata") viene assorbita da quella specifica."""
    merged = []
    for ev in sorted(events, key=lambda e: e["inizio"]):
        start = dt.datetime.fromisoformat(ev["inizio"])
        target = None
        for m in reversed(merged):
            if m["categoria"] != ev["categoria"] or m["competizione"] != ev["competizione"]:
                continue
            m_start = dt.datetime.fromisoformat(m["inizio"])
            if m_start.date() != start.date():
                continue
            same_event = m["evento"] == ev["evento"] and (start - m_start) <= dt.timedelta(hours=6)
            generic = ev["evento"] == ev["competizione"] or m["evento"] == m["competizione"]
            if same_event or (generic and m_start == start):
                target = m
                break
        if target is None:
            merged.append(ev)
            continue
        if target["evento"] == target["competizione"] and ev["evento"] != ev["competizione"]:
            for k in ("titolo", "evento"):
                target[k] = ev[k]
        names = {norm(c["nome"]) for c in target["canali"]}
        for c in ev["canali"]:
            if norm(c["nome"]) not in names:
                target["canali"].append(c)
    return merged


def virgilio_events(cfg, categories, sub_by, tz, numbers):
    if not cfg.get("attivo", True):
        return []
    try:
        raw = load_virgilio(cfg.get("url", VIRGILIO_URL), tz)
    except Exception as exc:
        log("Virgilio non disponibile: %s" % exc)
        return []
    excl_sport = [s.lower() for s in cfg.get("sport_esclusi", [])]
    excl_event = [s.lower() for s in cfg.get("eventi_esclusi", [])]
    out = []
    for e in raw:
        sport_low = e["sport"].lower()
        text_low = (e["competizione"] + " " + e["evento"]).lower()
        if any(s in sport_low for s in excl_sport) or any(s in text_low for s in excl_event):
            continue
        cat = pick_category(e["sport"], categories)
        mode = sub_by.get(cat, "competizione")
        if mode == "sport":
            sub = folder_name(e["sport"])
        else:
            sub = folder_name(e["competizione"] or e["sport"])
            if "femminile" in sport_low and "femminile" not in sub.lower():
                sub += " femminile"
        start = e["start"]
        title = e["evento"]
        if e["competizione"] and e["competizione"] != e["evento"]:
            title = "%s: %s" % (folder_name(e["competizione"]), e["evento"])
        out.append({
            "titolo": title,
            "categoria": cat,
            "sottocartella": sub,
            "_ordine_sottocartella": 99,
            "sport": e["sport"],
            "competizione": e["competizione"],
            "evento": e["evento"],
            "inizio": start.isoformat(),
            "data": start.strftime("%d/%m/%Y"),
            "ora": start.strftime("%H:%M"),
            "canali": [{"nome": c, "numero": numbers.get(c, ""), "tipo": "diretta",
                        "orario": start.strftime("%Y-%m-%dT%H:%M"), "fonte": "virgilio"}
                       for c in e["canali"]],
            "fonte": "Virgilio Sport",
        })
    return merge_virgilio(out)


STREAMING_NAMES = ("sky go", "now tv", "now", "dazn", "prime video", "amazon", "infinity", "raiplay")


def team_tokens(text):
    stop = {"vs", "fc", "ac", "as", "us", "ss", "calcio", "u23", "next", "gen", "1913", "1919"}
    words = re.findall(r"[a-z]+", virgilio_norm(text))
    return {w for w in words if len(w) > 2 and w not in stop}


def virgilio_norm(text):
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def split_teams(title):
    parts = re.split(r"\s+vs\.?\s+|\s+-\s+|-", title, maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else (title, "")


def livesoccer_events(cfg, tz, numbers):
    if not cfg.get("attivo", True):
        return []
    local = os.environ.get("LIVESOCCER_FILE")
    try:
        if local and os.path.exists(local):
            with open(local, encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            req = urllib.request.Request(cfg["url"], headers={"User-Agent": "calendario-sport"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log("LiveSoccer non disponibile: %s" % exc)
        return []
    items = data.get("eventi", []) if isinstance(data, dict) else data
    wanted = cfg.get("competizioni", [])
    out = []
    for e in items:
        comp = e.get("competizione", "")
        if wanted and comp not in wanted:
            continue
        try:
            start = dt.datetime.strptime("%s %s" % (e["data"], e["ora"]), "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        except (KeyError, ValueError):
            continue
        canali = []
        for name in e.get("canali", []):
            low = name.lower()
            tipo = "streaming" if any(low.startswith(s) for s in STREAMING_NAMES) else "diretta"
            canali.append({"nome": name, "numero": numbers.get(name, ""), "tipo": tipo,
                           "orario": start.strftime("%Y-%m-%dT%H:%M"), "fonte": "livesoccer"})
        out.append({
            "titolo": "%s: %s" % (comp, e.get("titolo", "")),
            "categoria": "Calcio",
            "sottocartella": comp,
            "_ordine_sottocartella": wanted.index(comp) if comp in wanted else 50,
            "sport": "Calcio",
            "competizione": comp,
            "evento": e.get("titolo", ""),
            "inizio": start.isoformat(),
            "data": start.strftime("%d/%m/%Y"),
            "ora": start.strftime("%H:%M"),
            "canali": canali,
            "canali_mondo": e.get("canali_mondo", []),
            "fonte": "LiveSoccerTV",
        })
    log("LiveSoccer: %d partite" % len(out))
    return out


def merge_football(soccer, others, competitions):
    """Le partite di Serie A/B/C trovate anche su Virgilio vengono unite a quelle di
    LiveSoccer: si aggiungono i canali mancanti (es. Rai o TV8 in chiaro) e il doppione sparisce."""
    if not soccer:
        return others
    comps = {c.lower() for c in competitions}
    kept = []
    for ev in others:
        is_target = (ev["categoria"] == "Calcio" and ev["sport"].lower() == "calcio"
                     and folder_name(ev["competizione"]).lower() in comps)
        if not is_target:
            kept.append(ev)
            continue
        home, away = split_teams(ev["evento"])
        th, ta = team_tokens(home), team_tokens(away)
        match = None
        for s in soccer:
            if s["inizio"][:10] != ev["inizio"][:10]:
                continue
            sh, sa = split_teams(s["evento"])
            if th & team_tokens(sh) and ta & team_tokens(sa):
                match = s
                break
        if match is None:
            ev["sottocartella"] = folder_name(ev["competizione"])
            ev["_ordine_sottocartella"] = competitions.index(ev["sottocartella"]) if ev["sottocartella"] in competitions else 50
            kept.append(ev)
            continue
        names = {virgilio_norm(c["nome"]) for c in match["canali"]}
        for c in ev["canali"]:
            if virgilio_norm(c["nome"]) not in names and c["nome"].lower() != "sky":
                match["canali"].append(c)
    return kept


def clean(event):
    return {k: val for k, val in event.items() if not k.startswith("_")}


def build():
    cfg = CONFIG
    numbers = MOTOR_CONFIG.get("numeri_canali", {})
    tz = ZoneInfo(cfg.get("fuso", "Europe/Rome"))
    now = dt.datetime.now(tz)
    since = now - dt.timedelta(hours=cfg.get("ore_indietro", 3))
    categories = cfg["categorie"]

    ls_cfg = cfg.get("livesoccer", {})
    soccer = livesoccer_events(ls_cfg, tz, numbers)
    others = virgilio_events(cfg.get("virgilio", {}), categories,
                             cfg.get("sottocartelle_per", {}), tz, numbers)
    others = merge_football(soccer, others, ls_cfg.get("competizioni", []))
    events = motor_events(cfg.get("motorsport", {}), tz, now) + soccer + others
    events = [e for e in events if dt.datetime.fromisoformat(e["inizio"]) >= since]
    events.sort(key=lambda e: (e["inizio"], e["categoria"], e["titolo"]))

    folders = []
    if cfg.get("cartella_oggi", True):
        today = []
        for e in events:
            if dt.datetime.fromisoformat(e["inizio"]).date() == now.date():
                item = clean(e)
                item["titolo"] = "[%s] %s" % (e["categoria"], e["titolo"])
                today.append(item)
        if today:
            folders.append({"nome": "Oggi", "totale": len(today), "eventi": today})

    for cat in categories:
        in_cat = [e for e in events if e["categoria"] == cat["nome"]]
        if not in_cat:
            continue
        subs = {}
        for e in in_cat:
            subs.setdefault(e["sottocartella"], []).append(e)
        ordered = sorted(subs.items(), key=lambda kv: (kv[1][0]["_ordine_sottocartella"], kv[1][0]["inizio"]))
        folders.append({
            "nome": cat["nome"],
            "totale": len(in_cat),
            "sottocartelle": [{"nome": name, "totale": len(evs), "eventi": [clean(e) for e in evs]}
                              for name, evs in ordered],
        })

    return {
        "aggiornato": now.isoformat(timespec="seconds"),
        "fonti": {
            "motori": "Fuori Traiettoria, Dizzle0987/motorsport-calendar, palinsesto TV8",
            "calcio_italiano": cfg.get("livesoccer", {}).get("url", ""),
            "altri_sport": VIRGILIO_URL,
        },
        "totale": len(events),
        "cartelle": folders,
    }


def main():
    data = build()
    old = None
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH, encoding="utf-8") as fh:
                old = json.load(fh)
        except ValueError:
            old = None
    if old and old.get("cartelle") == data["cartelle"]:
        log("Nessuna modifica, file non riscritto")
        return
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, OUT_PATH)
    log("Scritti %d eventi in %d cartelle" % (data["totale"], len(data["cartelle"])))


if __name__ == "__main__":
    main()
