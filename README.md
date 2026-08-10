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

## Umami (statystyki, bez ciasteczek i bez banera zgody)

`docker compose up -d` z obrazem `ghcr.io/umami-software/umami:postgresql-latest` + Postgres.
Potem odkomentuj w `hugo.toml` parametry `umami` i `umamiId`.

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

## Sprawdzone na telefonie 375 px

Brak przewijania w poziomie, tekst bazowy 18 px, h1 38 px, wszystkie cele dotykowe 48 px.
Kontrasty palety policzone wzorem WCAG — wartości w komentarzach `assets/css/main.css`.

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
