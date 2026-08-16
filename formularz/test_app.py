"""Sprawdzenie odbioru zgłoszeń: python test_app.py (wymaga flask i Pillow).

Nie idzie do obrazu Dockera. Pilnuje rzeczy, które już raz zawiodły: limit z IP
liczący nieudane próby, znak nowej linii w polu e-mail wysadzający cały e-mail
do Koła, oraz potwierdzenia wychodzące na adres, który adresem nie jest.
"""
import io
import sys
import pathlib
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import app  # noqa: E402

from PIL import Image  # noqa: E402

app.KATALOG = pathlib.Path(tempfile.mkdtemp()) / "zgloszenia"
WYSLANE = []
app.wyslij_smtp = lambda wiadomosc: WYSLANE.append(wiadomosc)
klient = app.app.test_client()

BAZA = {"imie_nazwisko": "Testowa Osoba", "adres": "Czemierniki 1", "telefon": "500 600 700",
        "email": "test@example.com", "opis": "Opis ogrodu",
        "relacja": "Własny ogród (właściciel lub użytkownik)",
        "osw_karta": "TAK", "osw_wykorzystanie": "TAK", "osw_wizerunek": "TAK"}


def zdjecie(numer):
    bufor = io.BytesIO()
    Image.new("RGB", (40, 30), (20, 120, 40)).save(bufor, "JPEG")
    bufor.seek(0)
    return (bufor, f"ogrod{numer}.jpg")


def zglos(ile_zdjec=4, **nadpisz):
    dane = dict(BAZA, **nadpisz)
    dane["zdjecia"] = [zdjecie(i) for i in range(ile_zdjec)]
    return klient.post("/api/zgloszenie", data=dane, content_type="multipart/form-data")


def czysto():
    app._ostatnie.clear()
    WYSLANE.clear()


def sprawdz():
    czysto()
    assert zglos(ile_zdjec=3).status_code == 400, "trzy zdjęcia to za mało"
    assert zglos(osw_wykorzystanie="").status_code == 400, "bez licencji na zdjęcia nie przyjmujemy"
    assert zglos(osw_wizerunek="").status_code == 200, "zgoda na wizerunek jest dobrowolna"

    czysto()
    for _ in range(5):
        zglos(ile_zdjec=3)
    assert zglos().status_code == 200, "nieudane próby nie mogą wyczerpać limitu z IP"

    czysto()
    assert zglos().status_code == 200
    for _ in range(4):
        zglos()
    assert zglos().status_code == 429, "po pięciu udanych zgłoszeniach limit ma zadziałać"

    czysto()
    zglos(email="ktos@example.com\nBcc: ofiara@example.com")
    assert len(WYSLANE) == 1, "wstrzyknięcie nagłówka nie może zabrać maila do Koła"
    assert "Reply-To" not in WYSLANE[0], "zły adres nie trafia do nagłówka"

    czysto()
    zglos(email="nie-jest-adresem")
    assert len(WYSLANE) == 1, "potwierdzenie tylko na poprawny adres"

    czysto()
    zglos(email="kasia@example.com")
    assert [w["To"] for w in WYSLANE] == [app.MAIL_TO, "kasia@example.com"], "mail do Koła i potwierdzenie"

    czysto()
    klient.post("/api/kontakt", data={"imie": "Anna", "kontakt": "anna@example.com",
                                      "miejscowosc": "Wohyń", "temat": "dolacz"})
    assert len(WYSLANE) == 2, "zapis do Klubu: mail do Koła i powitanie"
    tresc = WYSLANE[0].get_body(preferencelist=("plain",)).get_content()
    assert "Wohyń" in tresc, "miejscowość musi dojechać do Koła"

    czysto()
    klient.post("/api/kontakt", data={"imie": "Jan", "kontakt": "500 600 700", "temat": "dolacz"})
    assert len(WYSLANE) == 1, "sam telefon: bez powitania mailem"

    czysto()
    assert klient.post("/api/kontakt", data={"imie": "Bot", "kontakt": "a@b.pl",
                                             "strona_www": "spam"}).get_json()["ok"] is True
    assert not WYSLANE, "pułapka na boty nie wysyła maila"

    print("Wszystkie sprawdzenia przeszły.")


if __name__ == "__main__":
    sprawdz()
