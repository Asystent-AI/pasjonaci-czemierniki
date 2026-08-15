# pasjonaci.czemierniki.org

Hugo (jedna binarka, bez npm) + Sveltia CMS (panel dla Beaty, działa na tablecie i telefonie)
+ Caddy na Hetznerze + Umami na statystyki.

## Praca lokalna

```bash
../.bin/hugo.exe server
```

Podgląd na http://localhost:1313. Binarka Hugo leży w `.bin/` — wersja przypięta na **0.164.0**,
żeby build za rok użył dokładnie tego samego pliku.

Publikacja:

```bash
../.bin/hugo.exe --destination public && rsync -avz --delete public/ user@serwer:/var/www/pasjonaci/
```

## Zanim wejdzie na serwer

1. Skopiuj do `static/dokumenty/` dwa pliki z `fg.pl`:
   - `REGULAMIN_KONKURSU_OGRODNICZEGO_2026.pdf` → `regulamin-2026.pdf`
   - `ZALACZNIK_NR_1.pdf` → `karta-zgloszeniowa-2026.pdf`
2. Sprawdź linki na `/konkurs/` — bez tych plików prowadzą donikąd.

## Caddy

```
pasjonaci.czemierniki.org {
    root * /var/www/pasjonaci
    encode gzip
    file_server
    header /css/* Cache-Control "public, max-age=31536000, immutable"
}
```

Certyfikat Caddy załatwia sam. `systemctl reload caddy`.

## Umami (statystyki, bez ciasteczek i bez banera zgody) — WDROŻONE 15.08.2026

Stoi na serwerze w `/opt/umami` (compose: `umami` + `umami-db`, Postgres 16, wolumen
`umami_umami-db-data`). Hasło admina w `/opt/umami/haslo-admina.txt` (chmod 600), sekrety
w `/opt/umami/.env`.

Routing jest **dwutorowy** i to nie jest ozdobnik:

* **Panel:** `https://statystyki.czemierniki.org` (osobny router Traefika, bez modyfikacji ścieżki).
* **Tracker:** `https://pasjonaci.czemierniki.org/statystyki/script.js`, czyli z **własnej domeny**,
  żeby blokery reklam nie zjadały pomiarów. Traefik przepuszcza tam **wyłącznie dwie ścieżki**
  (`Path(/statystyki/script.js) || Path(/statystyki/api/send)`) i zdejmuje prefiks
  middlewarem `stat-strip`.

Zawężenie do dwóch ścieżek jest **wymogiem bezpieczeństwa**, nie estetyki: przy zwykłym
`PathPrefix(/statystyki)` całe API panelu (łącznie z `/api/auth/login`) było publicznie
dostępne pod adresem strony.

**Pułapka:** zmienna `BASE_PATH` **nie działa** w gotowym obrazie Dockera. Next.js wkompilowuje
prefiks przy budowaniu, więc obraz z Docker Huba zawsze serwuje spod `/`. Stąd StripPrefix
zamiast `BASE_PATH`, a panel pod subdomeną zamiast pod ścieżką (panel ciągnie assety z `/_next/`
i pod ścieżką by się rozsypał).

Identyfikator strony i adres skryptu siedzą w `hugo.toml` (`umamiId`, `umami`), hook
w `layouts/baseof.html`. Zdarzenia konwersji wysyła `assets/js/strona.js` funkcją `slad()`:
`zgloszenie-konkursowe`, `wiadomosc` (z tematem), `telefon`, `e-mail`, `pobranie-pdf`.

## Sveltia CMS (panel dla Beaty) — etap 2

1. Repo tego katalogu na GitHubie, konto dla Beaty z dostępem tylko do niego.
2. `sveltia-cms-auth` na darmowym Cloudflare Workers (OAuth).
3. `static/admin/index.html` + `static/admin/config.yml` z transformacją zdjęć:

```yaml
media_libraries:
  default:
    config:
      transformations:
        raster_image: { format: webp, quality: 85, width: 2048, height: 2048 }
      max_file_size: 1024000
      slugify_filename: true
```

Zdjęcie z telefonu ląduje w repo już odchudzone — to jedyne miejsce, gdzie da się zatrzymać
pliki po 8 MB.

Awaryjnie: `config.yml` jest zgodny z Decap CMS. Gdyby Sveltia padła, podmieniasz jeden skrypt
bez ruszania treści.

## Sprawdzone na telefonach — audyt 15.08.2026

Matryca `responsive-audit` (iPhone SE, iPhone 15, Pixel 7, Galaxy S24, iPad mini, 320 → 1920 px)
na żywym adresie: **zero usterek krytycznych i blokujących** na wszystkich pięciu podstronach.
Pełny raport: `output/2026-08-15-audyt-mobilny-strony-klubu.md` w katalogu projektu.

Progi, które trzeba trzymać przy kolejnych zmianach:

* tekst bazowy 17 px, h1 33,6 px przy 360 px, cele dotykowe **min. 44 px** (kwadraciki zgód 24 px,
  ale klika się całą etykietę);
* kontrast tekstu min. 4,5:1, ramek pól min. 3:1 (`--linia-pola`);
* zero poziomego przewijania — sprawdzaj `scrollWidth` przy 320, 360 i 412 px.

Pułapki, które już raz kosztowały czas i wracają przy każdej większej zmianie:

* **poświata `::before` pod zdjęciem** wychodzi 6% poza kadr — sekcja z nią musi mieć
  `overflow: hidden` (`.bohater` i `.strona-glowa` mają);
* **plakietka i znak w hero** nie mieszczą się obok siebie **poniżej 1000 px**, nie 760 —
  osobny blok `@media (max-width: 1000px)`;
* **elementem flex w nagłówku jest kotwica, nie `img`** — bez `flex: none` odznaka robi się elipsą;
* **animacje wejścia `.odslon`** działają tylko przy klasie `js` na `<html>` (skrypt w `<head>`),
  inaczej bez JS sekcje zostają niewidoczne;
* **pole pułapki na roboty** chowaj klasą `.pulapka` (`clip-path`), nigdy przez `left: -9999px` —
  rozpycha layout na Androidzie.

Kontrasty palety policzone wzorem WCAG — wartości w komentarzach `assets/css/main.css`.

## Zdjęcia: trzy warianty

`narzedzia/assety_www.py` generuje `-d` (1600 px), `-m` (800 px) i `-s` (500 px). Galeria
i miniatury kart podają `srcset` z `-s` i `-m`; zdjęcia w nagłówkach mają `-m` i `-d`.

W hero i w nagłówkach podstron `sizes` na telefonie **celowo zaniża slot** (`60vw` przy realnych
`92vw`), żeby nawet ekran 3× wziął plik 800 px zamiast 1600 px. Przy 358 px szerokości daje to
2,2-krotne zagęszczenie, czyli ostrość bez różnicy dla oka, a 580 KB mniej do pobrania.

## Wdrożone 10.08.2026 (Coolify/Traefik, nie Caddy)

Serwer: root@204.168.196.86 (agent-ai). Portami 80/443 rządzi coolify-proxy (Traefik),
więc strona chodzi jako kontener `pasjonaci-czemierniki` (nginx:alpine, restart unless-stopped,
sieć `coolify`, labele Traefik z certresolver=letsencrypt) serwujący /var/www/pasjonaci.

Aktualizacja strony (bez restartu kontenera):

```bash
cd strona && ../.bin/hugo.exe --quiet --destination public --baseURL https://pasjonaci.czemierniki.org/
tar czf - -C public . | ssh root@204.168.196.86 "tar xzf - -C /var/www/pasjonaci"
```

Kontener stoi poza panelem Coolify (Traefik czyta labele z sieci coolify). Działa i przeżyje
restart serwera; przeniesienie pod panel Coolify = opcjonalny porządek na później.
