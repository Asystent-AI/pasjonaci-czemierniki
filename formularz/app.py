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
from html import escape
from pathlib import Path

from flask import Flask, request, jsonify

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024  # 40 MB na całe zgłoszenie

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("formularz")

KATALOG = Path(os.environ.get("KATALOG_ZGLOSZEN", "/dane/zgloszenia"))
MAIL_TO = os.environ.get("MAIL_TO", "kgw.czemierniki@gmail.com")

# Logo w mailu: odznaka Klubu, dołączana jako obraz osadzony (cid), nie link.
# Klienty pocztowe domyślnie blokują obrazy z sieci, osadzony pokazuje się od razu.
LOGO = Path(__file__).with_name("logo-mail.png")
TELEFON_KLUBU = "795 716 644"
FIOLET, FIOLET_CIEMNY, ZIELEN, ATRAMENT, SZARY = "#5A2495", "#36105A", "#3A7322", "#241533", "#6B6078"

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
    ("osw_wykorzystanie", "Licencja na zdjęcia ogrodu i opis (§ 8 ust. 2 Regulaminu)"),
    ("osw_wizerunek", "ZGODA NA WIZERUNEK I NAZWISKO PRZY WYNIKACH (dobrowolna)"),
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
    # Dwa pierwsze oświadczenia są warunkiem udziału (akceptacja Regulaminu i licencja na
    # zdjęcia z § 8 ust. 2). Trzecie, zgoda na wizerunek, MUSI zostać dobrowolne: wymuszona
    # jest nieważna (art. 7 ust. 4 RODO). Wszystkie trzy zapisujemy, bo zgodę trzeba umieć
    # wykazać (art. 7 ust. 1 RODO), a walidację w przeglądarce da się obejść.
    for klucz in ("osw_karta", "osw_wykorzystanie", "osw_wizerunek"):
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
        wyslij_email(dane, folder, kiedy, zdjecia=len(zapisane), zgoda_pliku=bool(zgoda))
    except Exception:
        log.exception("Wysyłka e-maila nie powiodła się, zgłoszenie zostało na dysku: %s", folder)

    # 3. Potwierdzenie dla zgłaszającego. Osobna próba: jego skrzynka może odrzucić
    # wiadomość, a to nie może wpłynąć na maila do Koła ani na odpowiedź formularza.
    try:
        potwierdz_zgloszenie(dane)
    except Exception:
        log.exception("Nie udało się wysłać potwierdzenia do zgłaszającego")

    return jsonify(ok=True)


def szkielet(naglowek: str, wprowadzenie: str, srodek: str, stopka: str = "") -> str:
    """Mail w jednej kolumnie na tabelach: Gmail, Outlook i poczta na telefonie
    renderują to tak samo, a flexbox i grid w wielu klientach nie działają."""
    return f"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F5F2F8;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F5F2F8;padding:24px 12px;">
<tr><td align="center">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0"
    style="width:600px;max-width:100%;background:#FFFFFF;border-radius:16px;overflow:hidden;
    font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:{ATRAMENT};">
    <tr><td style="background:{FIOLET_CIEMNY};padding:22px 28px;">
      <table role="presentation" cellpadding="0" cellspacing="0"><tr>
        <td style="padding-right:14px;"><img src="cid:logo-klubu" width="52" height="52" alt=""
          style="display:block;border-radius:50%;background:#fff;"></td>
        <td style="color:#FFFFFF;font-size:17px;font-weight:700;line-height:1.3;">{naglowek}
          <div style="font-size:13px;font-weight:400;color:#D9C4EE;padding-top:3px;">{wprowadzenie}</div>
        </td>
      </tr></table>
    </td></tr>
    <tr><td style="padding:24px 28px 8px;font-size:15px;line-height:1.55;">{srodek}</td></tr>
    <tr><td style="padding:14px 28px 26px;font-size:12px;line-height:1.6;color:{SZARY};
      border-top:1px solid #EDE8F3;">{stopka}</td></tr>
  </table>
  <div style="font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
    font-size:11px;color:#8B8296;padding:14px 8px 0;">Klub Pasjonatów Ogrodnictwa przy Kole Gospodyń
    Wiejskich Czemierniki &middot; pasjonaci.czemierniki.org</div>
</td></tr></table>
</body></html>"""


def sekcja(tytul: str, wiersze: list) -> str:
    """Nagłówek sekcji i tabelka etykieta/wartość. Puste wartości wypadają."""
    widoczne = [(e, w) for e, w in wiersze if w]
    if not widoczne:
        return ""
    komorki = "".join(
        f'<tr><td style="padding:5px 12px 5px 0;color:{SZARY};font-size:13px;white-space:nowrap;'
        f'vertical-align:top;">{e}</td>'
        f'<td style="padding:5px 0;font-weight:600;vertical-align:top;">{w}</td></tr>'
        for e, w in widoczne)
    return (f'<div style="font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;'
            f'color:{ZIELEN};padding:6px 0 6px;">{tytul}</div>'
            f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
            f'style="font-size:15px;margin-bottom:16px;">{komorki}</table>')


def ramka(tresc: str, kolor: str, tlo: str) -> str:
    return (f'<div style="border-left:4px solid {kolor};background:{tlo};border-radius:0 10px 10px 0;'
            f'padding:12px 16px;margin:4px 0 18px;font-size:14px;line-height:1.55;">{tresc}</div>')


def zloz_wiadomosc(temat: str, tekst: str, tresc_html: str, do: str = MAIL_TO,
                   odpowiedz_do: str = "") -> EmailMessage:
    """Wersja tekstowa i HTML w jednej wiadomości, logo osadzone przy HTML-u."""
    wiadomosc = EmailMessage()
    wiadomosc["Subject"] = temat
    wiadomosc["To"] = do
    if odpowiedz_do:
        wiadomosc["Reply-To"] = odpowiedz_do
    wiadomosc.set_content(tekst)
    wiadomosc.add_alternative(tresc_html, subtype="html")
    if LOGO.exists():
        wiadomosc.get_payload()[1].add_related(
            LOGO.read_bytes(), "image", "png", cid="<logo-klubu>", filename="logo-klubu.png")
    return wiadomosc


def telefon_html(numer: str) -> str:
    czysty = re.sub(r"[^0-9+]", "", numer)
    return f'<a href="tel:{czysty}" style="color:{FIOLET};text-decoration:none;">{escape(numer)}</a>'


def wyslij_email(dane: dict, folder: Path, kiedy: datetime, zdjecia: int = 0,
                 zgoda_pliku: bool = False) -> None:
    cudzy = dane["relacja"].startswith("Zgłoszenie cudzego")
    linie = [
        "Nowe zgłoszenie do konkursu Najpiękniejszy Ogród Gminy Czemierniki 2026.",
        f"Wysłane przez formularz na stronie {kiedy:%d.%m.%Y o %H:%M}.",
        "",
    ]
    for klucz, etykieta in POLA:
        if dane[klucz]:
            linie.append(f"{etykieta}: {dane[klucz]}")
    linie += ["", f"Zdjęcia ogrodu w załączniku: {zdjecia}."]
    if dane["osw_wizerunek"] == "TAK":
        linie.append("Zgoda na wizerunek i na podanie imienia i nazwiska przy wynikach: JEST.")
    else:
        linie.append("UWAGA: BRAK zgody na wizerunek. Publikujemy sam ogród, a przy wynikach "
                     "tylko miejscowość. Zgodę można zebrać podczas wizytacji, na kartce do podpisu.")
    linie.append(f"Kopia zgłoszenia na serwerze: {folder}")

    kontakt_html = telefon_html(dane["telefon"])
    if dane["email"]:
        kontakt_html += (f'<br><a href="mailto:{escape(dane["email"])}" '
                         f'style="color:{FIOLET};">{escape(dane["email"])}</a>')
    srodek = sekcja("Zgłaszający", [
        ("Imię i nazwisko", escape(dane["imie_nazwisko"])),
        ("Kontakt", kontakt_html),
        ("Adres zamieszkania", escape(dane["adres"])),
    ])
    # przy cudzym ogrodzie adresem ogrodu jest ten z sekcji B, a nie adres zgłaszającego
    adres_ogrodu = dane["adres_ogrodu"] or (dane["wl_adres_ogrodu"] if cudzy else "") or dane["adres"]
    srodek += sekcja("Zgłoszony ogród", [
        ("Adres ogrodu", escape(adres_ogrodu)),
        ("Zgłoszenie", escape(dane["relacja"])),
        ("Właściciel", escape(dane["wl_imie_nazwisko"]) if cudzy else ""),
        ("Telefon właściciela", telefon_html(dane["wl_telefon"]) if cudzy and dane["wl_telefon"] else ""),
        ("Zgoda właściciela", ("w załączniku" if zgoda_pliku else
                               "<b style='color:#A4243B'>BRAK PLIKU</b>") if cudzy else ""),
        ("Zdjęcia", f"{zdjecia} szt. w załączniku tej wiadomości"),
    ])
    srodek += (f'<div style="font-size:12px;font-weight:700;letter-spacing:.08em;'
               f'text-transform:uppercase;color:{ZIELEN};padding:6px 0 6px;">Opis ogrodu</div>'
               f'<div style="background:#F6FAEE;border-radius:10px;padding:14px 16px;margin-bottom:18px;'
               f'font-size:14px;line-height:1.6;white-space:pre-wrap;">{escape(dane["opis"])}</div>')
    if dane["osw_wizerunek"] == "TAK":
        srodek += ramka(
            f"<b style='color:{ZIELEN}'>Zgoda na wizerunek: JEST.</b><br>"
            "Można publikować zdjęcia z wizytacji i finału oraz podać imię i nazwisko przy wynikach.",
            ZIELEN, "#F6FAEE")
    else:
        srodek += ramka(
            "<b style='color:#A4243B'>Zgoda na wizerunek: BRAK.</b><br>"
            "Publikujemy sam ogród, a przy wynikach podajemy tylko miejscowość. Zgodę można "
            "zebrać podczas wizytacji, na kartce do podpisu.",
            "#C4405A", "#FDF0F3")

    stopka = ("Oświadczenia obowiązkowe (Regulamin, klauzula RODO, prawa autorskie, licencja "
              "na zdjęcia z § 8 ust. 2) zostały zaznaczone, bez nich formularz nie przyjmuje "
              f"zgłoszenia.<br>Kopia zgłoszenia wraz ze zdjęciami: <code>{escape(str(folder))}</code>")

    wiadomosc = zloz_wiadomosc(
        f"Konkurs ogrodowy: zgłoszenie od {dane['imie_nazwisko']}",
        "\n".join(linie),
        szkielet("Nowe zgłoszenie do konkursu",
                 f"Najpiękniejszy Ogród Gminy Czemierniki 2026 &middot; {kiedy:%d.%m.%Y, godz. %H:%M}",
                 srodek, stopka),
        odpowiedz_do=dane["email"])

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


def potwierdz_zgloszenie(dane: dict) -> None:
    """Potwierdzenie dla zgłaszającego. Bez niego człowiek nie ma żadnego śladu,
    że zgłoszenie doszło, a formularz nie daje nic do wydrukowania."""
    if not dane["email"]:
        return
    imie = dane["imie_nazwisko"].split()[0] if dane["imie_nazwisko"] else ""
    tekst = "\n".join([
        f"{imie}, dziękujemy za zgłoszenie ogrodu do konkursu Najpiękniejszy Ogród Gminy "
        "Czemierniki 2026.",
        "",
        "Co dalej:",
        "1. Komisja Konkursowa sprawdza zgłoszenie i wybiera ogrody do wizytacji.",
        "2. Zadzwonimy, żeby uzgodnić termin wizyty w dniach 18-21 sierpnia 2026.",
        "3. Wyniki ogłaszamy 22 sierpnia na scenie Dożynek Gminno-Parafialnych w Czemiernikach.",
        "",
        f"Pytania: {TELEFON_KLUBU} albo {MAIL_TO}.",
        "Klub Pasjonatów Ogrodnictwa przy KGW Czemierniki",
    ])
    kroki = "".join(
        f'<tr><td style="padding:0 12px 12px 0;vertical-align:top;"><div style="width:26px;height:26px;'
        f'border-radius:50%;background:{FIOLET};color:#fff;font-size:14px;font-weight:700;'
        f'text-align:center;line-height:26px;">{n}</div></td>'
        f'<td style="padding:0 0 12px;font-size:15px;line-height:1.5;vertical-align:top;">{t}</td></tr>'
        for n, t in enumerate([
            "Komisja Konkursowa sprawdza zgłoszenie i wybiera ogrody do wizytacji.",
            "Dzwonimy, żeby uzgodnić termin wizyty. Wizytacje trwają <b>18–21 sierpnia</b>.",
            "Wyniki ogłaszamy <b>22 sierpnia</b> na scenie Dożynek Gminno-Parafialnych.",
        ], start=1))
    srodek = (f'<p style="margin:0 0 16px;font-size:16px;">{escape(imie)}, dziękujemy! '
              "Twoje zgłoszenie do konkursu dotarło do nas w komplecie.</p>"
              f'<div style="font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;'
              f'color:{ZIELEN};padding:4px 0 10px;">Co dalej</div>'
              f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%">{kroki}</table>'
              + ramka("Zgłoszony ogród: <b>" + escape(dane["adres_ogrodu"] or dane["adres"]) + "</b>",
                      FIOLET, "#F7F2FC"))
    stopka = (f"Masz pytania? Zadzwoń pod {telefon_html(TELEFON_KLUBU)} albo odpisz na tę wiadomość.<br>"
              "Klub Pasjonatów Ogrodnictwa przy Kole Gospodyń Wiejskich Czemierniki.")
    wyslij_smtp(zloz_wiadomosc(
        "Potwierdzenie zgłoszenia do konkursu ogrodowego",
        tekst,
        szkielet("Zgłoszenie przyjęte", "Najpiękniejszy Ogród Gminy Czemierniki 2026", srodek, stopka),
        do=dane["email"], odpowiedz_do=MAIL_TO))


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
    miejscowosc = request.form.get("miejscowosc", "").strip()
    wiadomosc = request.form.get("wiadomosc", "").strip()
    temat = request.form.get("temat", "kontakt").strip()
    if not imie or not dane_kontaktowe:
        return jsonify(ok=False, blad="Podaj imię oraz telefon albo e-mail."), 400

    kiedy = datetime.now()
    folder = KATALOG.parent / "wiadomosci"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{kiedy:%Y%m%d-%H%M%S}-{bezpieczna_nazwa(imie, 'anonim')}.json").write_text(
        json.dumps({"imie": imie, "kontakt": dane_kontaktowe, "miejscowosc": miejscowosc,
                    "wiadomosc": wiadomosc, "temat": temat, "ip": ip, "kiedy": kiedy.isoformat()},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Zapisano wiadomość (%s) od: %s", temat, imie)

    tytuly = {
        "dolacz": f"Klub Pasjonatów: {imie} chce dołączyć",
        "sponsor": f"WSPÓŁPRACA: {imie} pyta o partnerstwo z Klubem",
    }
    naglowki = {
        "dolacz": ("Nowy chętny do Klubu", "Zapis przez formularz „Dołącz do Klubu”"),
        "sponsor": ("Pytanie o współpracę", "Formularz na stronie „Wesprzyj Klub”"),
    }
    tytul = tytuly.get(temat, f"Wiadomość ze strony Klubu od {imie}")
    naglowek, wprowadzenie = naglowki.get(temat, ("Wiadomość ze strony Klubu", "Formularz kontaktowy"))
    linie_tekstu = [
        f"Wiadomość wysłana przez formularz na stronie {kiedy:%d.%m.%Y o %H:%M}.",
        "",
        f"Imię i nazwisko: {imie}",
        f"Kontakt: {dane_kontaktowe}",
    ]
    if miejscowosc:
        linie_tekstu.append(f"Miejscowość: {miejscowosc}")
    linie_tekstu += ["", wiadomosc or "(bez treści, prośba o kontakt)"]
    tresc = "\n".join(linie_tekstu)
    mailem = "@" in dane_kontaktowe and " " not in dane_kontaktowe
    kontakt_html = (f'<a href="mailto:{escape(dane_kontaktowe)}" style="color:{FIOLET};">'
                    f'{escape(dane_kontaktowe)}</a>' if mailem else telefon_html(dane_kontaktowe))
    srodek = sekcja("Kto pisze", [
        ("Imię i nazwisko", escape(imie)),
        ("Kontakt", kontakt_html),
        ("Miejscowość", escape(miejscowosc)),
        ("Kiedy", f"{kiedy:%d.%m.%Y, godz. %H:%M}"),
    ])
    if wiadomosc:
        srodek += (f'<div style="font-size:12px;font-weight:700;letter-spacing:.08em;'
                   f'text-transform:uppercase;color:{ZIELEN};padding:6px 0 6px;">Wiadomość</div>'
                   f'<div style="background:#F6FAEE;border-radius:10px;padding:14px 16px;'
                   f'font-size:14px;line-height:1.6;white-space:pre-wrap;">{escape(wiadomosc)}</div>')
    else:
        srodek += ramka("Bez treści, sama prośba o kontakt.", FIOLET, "#F7F2FC")
    stopka = ("Odpowiedz na tę wiadomość albo zadzwoń, korzystając z kontaktu powyżej. "
              "Kopia leży na serwerze w katalogu wiadomości.")
    try:
        wyslij_smtp(zloz_wiadomosc(
            tytul, tresc,
            szkielet(naglowek, wprowadzenie, srodek, stopka),
            odpowiedz_do=dane_kontaktowe if mailem else ""))
    except Exception:
        log.exception("Wysyłka wiadomości kontaktowej nie powiodła się, kopia na dysku")

    # potwierdzenie dla piszącego, gdy zostawił adres e-mail
    if mailem and temat == "dolacz":
        try:
            potwierdz_zapis(imie, dane_kontaktowe)
        except Exception:
            log.exception("Nie udało się wysłać potwierdzenia zapisu do Klubu")

    return jsonify(ok=True)


def potwierdz_zapis(imie: str, adres: str) -> None:
    pierwsze = imie.split()[0] if imie else ""
    tekst = "\n".join([
        f"{pierwsze}, dziękujemy za zgłoszenie do Klubu Pasjonatów Ogrodnictwa.",
        "",
        "Odezwiemy się telefonicznie albo mailem i zaprosimy Cię na najbliższe spotkanie.",
        "Udział jest bezpłatny i nie wymaga członkostwa w Kole Gospodyń Wiejskich.",
        "",
        f"Pytania: {TELEFON_KLUBU} albo {MAIL_TO}.",
        "Klub Pasjonatów Ogrodnictwa przy KGW Czemierniki",
    ])
    srodek = (f'<p style="margin:0 0 14px;font-size:16px;">{escape(pierwsze)}, cieszymy się, '
              "że chcesz do nas dołączyć!</p>"
              '<p style="margin:0 0 14px;">Odezwiemy się do Ciebie i zaprosimy na najbliższe '
              "spotkanie. Nic nie musisz przygotowywać, wystarczy przyjść i posłuchać.</p>"
              + ramka("Udział w spotkaniach jest <b>bezpłatny</b>, nie trzeba należeć do Koła "
                      "Gospodyń Wiejskich ani mieszkać w Czemiernikach.", ZIELEN, "#F6FAEE"))
    stopka = (f"Masz pytania? Zadzwoń pod {telefon_html(TELEFON_KLUBU)} albo odpisz na tę wiadomość.<br>"
              "Terminy spotkań ogłaszamy też na profilu KGW Czemierniki na Facebooku.")
    wyslij_smtp(zloz_wiadomosc(
        "Zapisaliśmy Cię na najbliższe spotkanie Klubu",
        tekst,
        szkielet("Witamy w Klubie", "Klub Pasjonatów Ogrodnictwa Czemierniki", srodek, stopka),
        do=adres, odpowiedz_do=MAIL_TO))


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
