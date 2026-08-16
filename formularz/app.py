"""Odbiór zgłoszeń konkursowych z formularza na pasjonaci.czemierniki.org.

Każde zgłoszenie jest zapisywane na dysku (wolumen /dane), a następnie wysyłane
e-mailem, jeśli skonfigurowano SMTP w zmiennych środowiskowych:

  SMTP_HOST, SMTP_PORT (587 = STARTTLS, 465 = SSL), SMTP_USER, SMTP_PASS,
  MAIL_TO (domyślnie kgw.czemierniki@gmail.com), MAIL_FROM (domyślnie SMTP_USER)

Bez konfiguracji SMTP zgłoszenia lądują tylko na dysku i w logu pojawia się
ostrzeżenie. Dysk jest zawsze pierwszy: zgłoszenie mieszkańca nie może
przepaść przez chwilową awarię poczty.
"""
import os
import re
import json
import logging
import smtplib
import time
import unicodedata
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from flask import Flask, request, jsonify

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024  # 40 MB na całe zgłoszenie

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("formularz")

KATALOG = Path(os.environ.get("KATALOG_ZGLOSZEN", "/dane/zgloszenia"))
MAIL_TO = os.environ.get("MAIL_TO", "kgw.czemierniki@gmail.com")

WYMAGANE = ["imie_nazwisko", "adres", "telefon", "opis"]
POLA = [
    ("imie_nazwisko", "Imię i nazwisko zgłaszającego"),
    ("adres", "Adres zamieszkania"),
    ("telefon", "Telefon"),
    ("email", "E-mail"),
    ("adres_ogrodu", "Adres ogrodu (jeśli inny)"),
    ("relacja", "Relacja do ogrodu"),
    ("wl_imie_nazwisko", "Właściciel ogrodu"),
    ("wl_adres_ogrodu", "Adres ogrodu (właściciel)"),
    ("wl_telefon", "Telefon właściciela"),
    ("opis", "Opis ogrodu"),
    ("osw_karta", "Akceptacja Regulaminu i Klauzuli RODO, prawa autorskie do zdjęć"),
    ("osw_wykorzystanie", "Zgoda na publikację zdjęć, opisu i wizerunku"),
]

# ponytail: limit zgłoszeń per IP trzymany w pamięci procesu; przy jednym
# workerze gunicorna wystarcza, przy większej skali przenieść do redis/pliku
_ostatnie: dict = {}


def za_duzo_zgloszen(ip: str) -> bool:
    teraz = time.time()
    lista = [t for t in _ostatnie.get(ip, []) if teraz - t < 3600]
    _ostatnie[ip] = lista
    if len(lista) >= 5:
        return True
    lista.append(teraz)
    return False


def bezpieczna_nazwa(tekst: str, domyslna: str = "plik") -> str:
    tekst = unicodedata.normalize("NFKD", tekst).encode("ascii", "ignore").decode()
    tekst = re.sub(r"[^A-Za-z0-9._-]+", "-", tekst).strip("-.")
    return tekst[:80] or domyslna


@app.get("/api/zdrowie")
def zdrowie():
    smtp = "skonfigurowany" if os.environ.get("SMTP_HOST") else "BRAK (zapis tylko na dysk)"
    return jsonify(ok=True, smtp=smtp)


@app.post("/api/zgloszenie")
def zgloszenie():
    # pułapka na boty: pole niewidoczne dla ludzi
    if request.form.get("strona_www", "").strip():
        return jsonify(ok=True)

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
    if za_duzo_zgloszen(ip):
        return jsonify(ok=False, blad="Za dużo zgłoszeń z tego adresu. Spróbuj za godzinę."), 429

    dane = {klucz: request.form.get(klucz, "").strip() for klucz, _ in POLA}
    # oba oświadczenia odpowiadają sekcji E karty zgłoszeniowej i muszą dać się wykazać
    # (art. 7 ust. 1 RODO); sprawdzamy je też tutaj, bo walidację w przeglądarce da się obejść
    for klucz in ("osw_karta", "osw_wykorzystanie"):
        dane[klucz] = "TAK" if request.form.get(klucz) in ("TAK", "on", "true", "1") else "NIE"
    braki = [k for k in WYMAGANE if not dane[k]]
    if braki:
        return jsonify(ok=False, blad="Brakuje wymaganych pól: " + ", ".join(braki)), 400
    if dane["osw_karta"] != "TAK" or dane["osw_wykorzystanie"] != "TAK":
        return jsonify(ok=False, blad="Zgłoszenie wymaga zaznaczenia obu oświadczeń."), 400

    zdjecia = request.files.getlist("zdjecia")
    zdjecia = [z for z in zdjecia if z.filename]
    if not 4 <= len(zdjecia) <= 7:
        return jsonify(ok=False, blad="Zgłoszenie wymaga od 4 do 7 zdjęć ogrodu."), 400

    zgoda = request.files.get("zgoda_wlasciciela")
    if zgoda and not zgoda.filename:
        zgoda = None

    # 1. Zapis na dysk: zawsze, zanim spróbujemy czegokolwiek innego
    kiedy = datetime.now()
    folder = KATALOG / f"{kiedy:%Y%m%d-%H%M%S}-{bezpieczna_nazwa(dane['imie_nazwisko'], 'anonim')}"
    folder.mkdir(parents=True, exist_ok=True)

    zapisane = []
    for i, z in enumerate(zdjecia, 1):
        nazwa = f"zdjecie-{i}-{bezpieczna_nazwa(z.filename)}"
        z.save(folder / nazwa)
        zapisane.append(nazwa)
    if zgoda:
        nazwa_zgody = "zgoda-wlasciciela-" + bezpieczna_nazwa(zgoda.filename)
        zgoda.save(folder / nazwa_zgody)

    (folder / "zgloszenie.json").write_text(
        json.dumps({**dane, "ip": ip, "kiedy": kiedy.isoformat(), "zdjecia": zapisane},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Zapisano zgłoszenie: %s (%d zdjęć)", folder.name, len(zapisane))

    # 2. E-mail do organizatorów
    try:
        wyslij_email(dane, folder, kiedy)
    except Exception:
        log.exception("Wysyłka e-maila nie powiodła się, zgłoszenie zostało na dysku: %s", folder)

    return jsonify(ok=True)


def wyslij_email(dane: dict, folder: Path, kiedy: datetime) -> None:
    wiadomosc = EmailMessage()
    wiadomosc["Subject"] = f"Konkurs ogrodowy: zgłoszenie od {dane['imie_nazwisko']}"
    wiadomosc["To"] = MAIL_TO
    if dane["email"]:
        wiadomosc["Reply-To"] = dane["email"]

    linie = [
        "Nowe zgłoszenie do konkursu Najpiękniejszy Ogród Gminy Czemierniki 2026.",
        f"Wysłane przez formularz na stronie {kiedy:%d.%m.%Y o %H:%M}.",
        "",
    ]
    for klucz, etykieta in POLA:
        if dane[klucz]:
            linie.append(f"{etykieta}: {dane[klucz]}")
    linie += ["",
              "Oba oświadczenia z sekcji E karty zgłoszeniowej zostały zaznaczone: bez nich "
              "formularz nie przyjmuje zgłoszenia.",
              f"Kopia zgłoszenia na serwerze: {folder}"]
    wiadomosc.set_content("\n".join(linie))

    for plik in sorted(folder.iterdir()):
        if plik.suffix == ".json":
            continue
        surowe = plik.read_bytes()
        if plik.suffix.lower() == ".pdf":
            typ = ("application", "pdf")
        elif plik.suffix.lower() == ".png":
            typ = ("image", "png")
        else:
            typ = ("image", "jpeg")
        wiadomosc.add_attachment(surowe, maintype=typ[0], subtype=typ[1], filename=plik.name)

    wyslij_smtp(wiadomosc)


@app.post("/api/kontakt")
def kontakt():
    # pułapka na boty
    if request.form.get("strona_www", "").strip():
        return jsonify(ok=True)

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
    if za_duzo_zgloszen(ip):
        return jsonify(ok=False, blad="Za dużo wiadomości z tego adresu. Spróbuj za godzinę."), 429

    imie = request.form.get("imie", "").strip()
    dane_kontaktowe = request.form.get("kontakt", "").strip()
    wiadomosc = request.form.get("wiadomosc", "").strip()
    temat = request.form.get("temat", "kontakt").strip()
    if not imie or not dane_kontaktowe:
        return jsonify(ok=False, blad="Podaj imię oraz telefon albo e-mail."), 400

    kiedy = datetime.now()
    folder = KATALOG.parent / "wiadomosci"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{kiedy:%Y%m%d-%H%M%S}-{bezpieczna_nazwa(imie, 'anonim')}.json").write_text(
        json.dumps({"imie": imie, "kontakt": dane_kontaktowe, "wiadomosc": wiadomosc,
                    "temat": temat, "ip": ip, "kiedy": kiedy.isoformat()},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Zapisano wiadomość (%s) od: %s", temat, imie)

    tytuly = {
        "dolacz": f"Klub Pasjonatów: {imie} chce dołączyć",
        "sponsor": f"WSPÓŁPRACA: {imie} pyta o partnerstwo z Klubem",
    }
    tytul = tytuly.get(temat, f"Wiadomość ze strony Klubu od {imie}")
    tresc = "\n".join([
        f"Wiadomość wysłana przez formularz na stronie {kiedy:%d.%m.%Y o %H:%M}.",
        "",
        f"Imię i nazwisko: {imie}",
        f"Kontakt: {dane_kontaktowe}",
        "",
        wiadomosc or "(bez treści, prośba o kontakt)",
    ])
    try:
        wiadomosc_email = EmailMessage()
        wiadomosc_email["Subject"] = tytul
        wiadomosc_email["To"] = MAIL_TO
        if "@" in dane_kontaktowe and " " not in dane_kontaktowe:
            wiadomosc_email["Reply-To"] = dane_kontaktowe
        wiadomosc_email.set_content(tresc)
        wyslij_smtp(wiadomosc_email)
    except Exception:
        log.exception("Wysyłka wiadomości kontaktowej nie powiodła się, kopia na dysku")

    return jsonify(ok=True)


def wyslij_smtp(wiadomosc: EmailMessage) -> None:
    """Wspólna wysyłka: uzupełnia nadawcę i wysyła przez SMTP z env."""
    host = os.environ.get("SMTP_HOST")
    if not host:
        log.warning("SMTP nieskonfigurowany, wiadomość tylko na dysku")
        return
    port = int(os.environ.get("SMTP_PORT", "587"))
    uzytkownik = os.environ.get("SMTP_USER", "")
    haslo = os.environ.get("SMTP_PASS", "")
    nadawca = os.environ.get("MAIL_FROM", uzytkownik)
    if "From" not in wiadomosc:
        wiadomosc["From"] = f"Strona pasjonaci.czemierniki.org <{nadawca}>"
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=60) as s:
            if uzytkownik:
                s.login(uzytkownik, haslo)
            s.send_message(wiadomosc)
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.starttls()
            if uzytkownik:
                s.login(uzytkownik, haslo)
            s.send_message(wiadomosc)
    log.info("E-mail wysłany do %s: %s", wiadomosc["To"], wiadomosc["Subject"])


@app.errorhandler(413)
def za_duze(_):
    return jsonify(ok=False, blad="Załączniki są zbyt duże (limit 40 MB). Zmniejsz zdjęcia i spróbuj ponownie."), 413
