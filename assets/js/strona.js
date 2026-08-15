/* Klub Pasjonatów Ogrodnictwa Czemierniki: nawigacja, odsłanianie, galeria, formularz. */
(function () {
  'use strict';

  /* ---------- Statystyki: zdarzenia ---------- */
  function slad(nazwa, dane) {
    if (window.umami && typeof window.umami.track === 'function') window.umami.track(nazwa, dane);
  }

  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[href]');
    if (!a) return;
    var adres = a.getAttribute('href') || '';
    if (adres.indexOf('tel:') === 0) slad('telefon');
    else if (adres.indexOf('mailto:') === 0) slad('e-mail');
    else if (/\.pdf($|\?)/i.test(adres)) slad('pobranie-pdf', { plik: adres.split('/').pop() });
  });

  /* ---------- Menu mobilne ---------- */
  var guzik = document.querySelector('.menu-guzik');
  var menu = document.getElementById('menu');
  if (guzik && menu) {
    var przelacz = function (otwarte) {
      menu.classList.toggle('otwarte', otwarte);
      guzik.setAttribute('aria-expanded', otwarte ? 'true' : 'false');
    };
    guzik.addEventListener('click', function (e) {
      e.stopPropagation();
      przelacz(!menu.classList.contains('otwarte'));
    });
    /* tapnięcie obok menu i Escape zamykają je: na telefonie nie ma innego wyjścia
       niż trafienie w mały guzik z hamburgerem */
    document.addEventListener('click', function (e) {
      if (menu.classList.contains('otwarte') && !menu.contains(e.target)) przelacz(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && menu.classList.contains('otwarte')) { przelacz(false); guzik.focus(); }
    });
  }

  /* ---------- Odsłanianie sekcji przy przewijaniu ---------- */
  var elementy = document.querySelectorAll('.odslon');
  if ('IntersectionObserver' in window && elementy.length) {
    var obs = new IntersectionObserver(function (wpisy) {
      wpisy.forEach(function (w) {
        if (w.isIntersecting) { w.target.classList.add('widoczne'); obs.unobserve(w.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.15 });
    elementy.forEach(function (el) { obs.observe(el); });
  } else {
    elementy.forEach(function (el) { el.classList.add('widoczne'); });
  }

  /* ---------- Podgląd zdjęć: galeria oraz pojedyncze zdjęcia na podstronach ----------
     Lista zdjęć Klubu jedzie z data/galeria.yaml na każdą stronę, więc podgląd
     otwarty z nagłówka /konkurs pozwala przewinąć całą galerię. */
  var galeria = document.getElementById('galeria');
  var zdjeciaKlubu = [];
  var zrodloListy = document.getElementById('zdjecia-klubu');
  if (zrodloListy) { try { zdjeciaKlubu = JSON.parse(zrodloListy.textContent); } catch (e) { zdjeciaKlubu = []; } }
  var pojedyncze = Array.prototype.slice.call(document.querySelectorAll('img.powieksz'));

  if (galeria || (zdjeciaKlubu.length && pojedyncze.length)) {
    var strzalka = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" ' +
      'stroke-linecap="round" stroke-linejoin="round"><path d="m14.5 5-7 7 7 7"/></svg>';
    var dialog = document.createElement('dialog');
    dialog.className = 'podglad';
    dialog.setAttribute('aria-label', 'Podgląd zdjęć Klubu');
    dialog.innerHTML =
      '<button type="button" class="p-zamknij" aria-label="Zamknij podgląd">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">' +
      '<path d="M6 6l12 12M18 6 6 18"/></svg></button>' +
      '<button type="button" class="p-strzalka p-poprz" aria-label="Poprzednie zdjęcie">' + strzalka + '</button>' +
      '<img alt="">' +
      '<button type="button" class="p-strzalka p-nast" aria-label="Następne zdjęcie">' + strzalka + '</button>' +
      '<p class="p-licznik" aria-live="polite"></p>';
    document.body.appendChild(dialog);

    var duze = dialog.querySelector('img');
    var licznikZdjec = dialog.querySelector('.p-licznik');
    var teraz = 0;

    // lista podglądu: gdy na stronie jest galeria, bierzemy ją (kolejność kafelków),
    // w przeciwnym razie wspólną listę zdjęć Klubu
    var lista = galeria
      ? Array.prototype.map.call(galeria.querySelectorAll('a'), function (a) {
          return { duze: a.getAttribute('href'), alt: (a.querySelector('img') || {}).alt || '' };
        })
      : zdjeciaKlubu;

    function indeksPo(adres) {
      for (var i = 0; i < lista.length; i++) if (lista[i].duze === adres) return i;
      return -1;
    }

    function pokaz(i) {
      teraz = (i + lista.length) % lista.length;
      duze.src = lista[teraz].duze;
      duze.alt = lista[teraz].alt;
      licznikZdjec.textContent = (teraz + 1) + ' z ' + lista.length;
    }

    function otworz(i) { pokaz(i); dialog.showModal(); }

    if (galeria) {
      galeria.addEventListener('click', function (e) {
        var a = e.target.closest('a');
        if (!a) return;
        e.preventDefault();
        otworz(indeksPo(a.getAttribute('href')));
      });
    }

    pojedyncze.forEach(function (obrazek) {
      var adres = obrazek.getAttribute('data-duze');
      var i = indeksPo(adres);
      if (i < 0) { lista = lista.concat([{ duze: adres, alt: obrazek.alt }]); i = lista.length - 1; }
      obrazek.style.cursor = 'zoom-in';
      obrazek.setAttribute('role', 'button');
      obrazek.setAttribute('tabindex', '0');
      obrazek.addEventListener('click', function () { otworz(i); });
      obrazek.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); otworz(i); }
      });
    });
    dialog.addEventListener('click', function (e) {
      if (e.target.closest('.p-poprz')) pokaz(teraz - 1);
      else if (e.target.closest('.p-nast')) pokaz(teraz + 1);
      else if (e.target === dialog || e.target.closest('.p-zamknij')) dialog.close();
    });
    dialog.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowLeft') { e.preventDefault(); pokaz(teraz - 1); }
      if (e.key === 'ArrowRight') { e.preventDefault(); pokaz(teraz + 1); }
    });

    /* Na telefonie strzałki są za małe jak na kciuk: przesunięcie w bok zmienia zdjęcie,
       przesunięcie w dół zamyka podgląd. Tak działa każda galeria, której ludzie tu używali. */
    var startX = 0, startY = 0;
    dialog.addEventListener('touchstart', function (e) {
      startX = e.changedTouches[0].clientX; startY = e.changedTouches[0].clientY;
    }, { passive: true });
    dialog.addEventListener('touchend', function (e) {
      var dx = e.changedTouches[0].clientX - startX, dy = e.changedTouches[0].clientY - startY;
      if (Math.abs(dx) > 45 && Math.abs(dx) > Math.abs(dy)) pokaz(teraz + (dx < 0 ? 1 : -1));
      else if (dy > 90 && Math.abs(dy) > Math.abs(dx)) dialog.close();
    }, { passive: true });
  }

  /* ---------- Formularze kontaktowe (Kontakt, Dołącz) ---------- */
  document.querySelectorAll('form.formularz-mini').forEach(function (fm) {
    fm.addEventListener('submit', function (e) {
      e.preventDefault();
      var wynikMini = fm.querySelector('.wynik-wyslania');
      wynikMini.className = 'wynik-wyslania'; wynikMini.textContent = '';
      var poprawny = true;
      fm.querySelectorAll('[required]').forEach(function (p) {
        var puste = !p.value.trim();
        var pole = p.closest('.pole');
        if (pole) pole.classList.toggle('ma-blad', puste);
        if (puste) poprawny = false;
      });
      if (!poprawny) {
        var pierwszeZle = fm.querySelector('.pole.ma-blad');
        if (pierwszeZle) {
          pierwszeZle.scrollIntoView({ behavior: 'smooth', block: 'center' });
          var wejscieZle = pierwszeZle.querySelector('input, textarea');
          if (wejscieZle) wejscieZle.focus({ preventScroll: true });
        }
        return;
      }
      var guzik = fm.querySelector('button[type="submit"]');
      var napis = guzik.textContent;
      guzik.disabled = true;
      guzik.textContent = 'Wysyłamy…';
      fetch('/api/kontakt', { method: 'POST', body: new FormData(fm) })
        .then(function (r) { return r.json(); })
        .then(function (odp) {
          if (!odp.ok) { var e2 = new Error(''); e2.wlasny = odp.blad; throw e2; }
          wynikMini.className = 'wynik-wyslania sukces';
          wynikMini.textContent = fm.getAttribute('data-sukces');
          slad('wiadomosc', { temat: String(new FormData(fm).get('temat') || 'ogolny') });
          fm.reset();
        })
        .catch(function (err) {
          wynikMini.className = 'wynik-wyslania porazka';
          wynikMini.textContent = (err && err.wlasny) ||
            'Nie udało się wysłać wiadomości. Zadzwoń: 795 716 644 albo napisz na kgw.czemierniki@gmail.com.';
        })
        .finally(function () {
          guzik.disabled = false; guzik.textContent = napis;
          wynikMini.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
    });
  });

  /* ---------- Formularz konkursowy ---------- */
  var form = document.getElementById('formularz-konkursu');
  if (!form) return;

  var MIN_ZDJEC = 4, MAX_ZDJEC = 7, MAKS_BOK = 2000, JAKOSC = 0.85;
  var zdjecia = []; // { plik: Blob, nazwa: string, url: string }
  var pominiete = 0; // ile zdjęć z ostatniego wyboru nie zmieściło się w limicie

  var wrzutnia = document.getElementById('wrzutnia');
  var wejscie = document.getElementById('zdjecia');
  var miniatury = document.getElementById('miniatury');
  var licznik = document.getElementById('licznik-zdjec');
  var sekcjaB = document.getElementById('sekcja-b');
  var wynik = document.getElementById('wynik-wyslania');
  var pasek = document.getElementById('pasek-wysylki');
  var pasekWypelnienie = pasek.querySelector('div');
  var wyslijGuzik = form.querySelector('.wyslij');

  /* Sekcja B pokazywana przy zgłoszeniu cudzego ogrodu */
  form.querySelectorAll('input[name="relacja"]').forEach(function (r) {
    r.addEventListener('change', function () {
      sekcjaB.classList.toggle('widoczna', form.relacja.value === 'osoba_trzecia');
    });
  });

  /* Wrzutnia zdjęć */
  wrzutnia.addEventListener('click', function () { wejscie.click(); });
  wrzutnia.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); wejscie.click(); }
  });
  ['dragover', 'dragenter'].forEach(function (t) {
    wrzutnia.addEventListener(t, function (e) { e.preventDefault(); wrzutnia.classList.add('nad'); });
  });
  ['dragleave', 'drop'].forEach(function (t) {
    wrzutnia.addEventListener(t, function (e) { e.preventDefault(); wrzutnia.classList.remove('nad'); });
  });
  wrzutnia.addEventListener('drop', function (e) { dodajPliki(e.dataTransfer.files); });
  wejscie.addEventListener('change', function () { dodajPliki(wejscie.files); wejscie.value = ''; });

  function dodajPliki(lista) {
    /* Limit trzeba policzyć przed zmniejszaniem: zmniejsz() jest asynchroniczne, więc przy
       wyborze kilkunastu zdjęć naraz każde przechodziło test „zdjecia.length >= MAX” i do
       tablicy wpadał komplet. Serwer odrzucał zgłoszenie dopiero po całej wysyłce. */
    var obrazki = Array.prototype.slice.call(lista).filter(function (p) { return /^image\//.test(p.type); });
    var wolne = Math.max(0, MAX_ZDJEC - zdjecia.length);
    var odrzucone = obrazki.length - Math.min(obrazki.length, wolne);
    obrazki.slice(0, wolne).forEach(function (plik) {
      zmniejsz(plik).then(function (blob) {
        var url = URL.createObjectURL(blob);
        zdjecia.push({ plik: blob, nazwa: plik.name.replace(/\.\w+$/, '') + '.jpg', url: url });
        rysujMiniatury();
      });
    });
    pominiete = odrzucone;
    if (!wolne) rysujMiniatury();
  }

  /* Zmniejszanie zdjęcia w przeglądarce: krótszy upload na wiejskim internecie */
  function zmniejsz(plik) {
    return createImageBitmap(plik).then(function (bmp) {
      var skala = Math.min(1, MAKS_BOK / Math.max(bmp.width, bmp.height));
      var c = document.createElement('canvas');
      c.width = Math.round(bmp.width * skala);
      c.height = Math.round(bmp.height * skala);
      c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
      bmp.close();
      return new Promise(function (ok) {
        c.toBlob(function (blob) { ok(blob || plik); }, 'image/jpeg', JAKOSC);
      });
    }).catch(function () { return plik; }); // nie udało się zdekodować: wyślemy oryginał
  }

  function rysujMiniatury() {
    miniatury.innerHTML = '';
    zdjecia.forEach(function (z, i) {
      var fig = document.createElement('figure');
      var img = document.createElement('img');
      img.src = z.url; img.alt = 'Zdjęcie ' + (i + 1);
      var usun = document.createElement('button');
      usun.type = 'button'; usun.textContent = '×';
      usun.setAttribute('aria-label', 'Usuń zdjęcie ' + (i + 1));
      usun.addEventListener('click', function () {
        URL.revokeObjectURL(z.url); zdjecia.splice(i, 1); pominiete = 0; rysujMiniatury();
      });
      fig.appendChild(img); fig.appendChild(usun); miniatury.appendChild(fig);
    });
    var n = zdjecia.length;
    var slowo = (n === 1) ? 'zdjęcie' : (n >= 2 && n <= 4) ? 'zdjęcia' : 'zdjęć';
    licznik.textContent = (n < MIN_ZDJEC
      ? 'Dodano ' + n + ' z wymaganych 4–7 zdjęć.'
      : 'Dodano ' + n + ' ' + slowo + '. W porządku!' + (n < MAX_ZDJEC ? ' Możesz dodać jeszcze ' + (MAX_ZDJEC - n) + '.' : ''))
      + (pominiete ? ' Limit to ' + MAX_ZDJEC + ' zdjęć, więc ' + pominiete + ' z wybranych nie weszło.' : '');
    licznik.className = 'licznik-zdjec ' + (n >= MIN_ZDJEC && !pominiete ? 'ok' : 'za-malo');
  }

  /* Walidacja i wysyłka */
  function zaznaczBlad(id, jest) {
    var pole = document.getElementById(id);
    if (pole) pole.closest('.pole').classList.toggle('ma-blad', jest);
    return jest;
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    wynik.className = 'wynik-wyslania'; wynik.textContent = '';

    var bledy = [];
    if (zaznaczBlad('imie', !form.imie_nazwisko.value.trim())) bledy.push('imie');
    if (zaznaczBlad('adres', !form.adres.value.trim())) bledy.push('adres');
    if (zaznaczBlad('telefon', !form.telefon.value.trim())) bledy.push('telefon');
    var email = form.email.value.trim();
    if (zaznaczBlad('email', !!email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email))) bledy.push('email');
    if (zaznaczBlad('opis', !form.opis.value.trim())) bledy.push('opis');

    var cudzy = form.relacja.value === 'osoba_trzecia';
    if (cudzy) {
      if (zaznaczBlad('wl-imie', !form.wl_imie_nazwisko.value.trim())) bledy.push('wl-imie');
      if (zaznaczBlad('wl-adres', !form.wl_adres_ogrodu.value.trim())) bledy.push('wl-adres');
      if (zaznaczBlad('wl-telefon', !form.wl_telefon.value.trim())) bledy.push('wl-telefon');
      if (zaznaczBlad('zgoda-plik', !form.zgoda_wlasciciela.files.length)) bledy.push('zgoda-plik');
    }

    if (zdjecia.length < MIN_ZDJEC) {
      licznik.className = 'licznik-zdjec za-malo';
      licznik.textContent = 'Zgłoszenie wymaga od 4 do 7 zdjęć ogrodu. Dodano: ' + zdjecia.length + '.';
      bledy.push('zdjecia');
    }

    // tylko oświadczenia obowiązkowe; zgoda na wizerunek jest dobrowolna
    var zgody = form.querySelectorAll('.zgody input[type="checkbox"][required]');
    var brakZgod = Array.prototype.some.call(zgody, function (z) { return !z.checked; });
    // bez zaznaczenia samej ramki niezaznaczone oświadczenie ginęło na długiej stronie
    Array.prototype.forEach.call(zgody, function (z) {
      var ramka = z.closest('.zgoda');
      if (ramka) ramka.classList.toggle('ma-blad', !z.checked);
    });
    if (brakZgod) {
      bledy.push('zgody');
      wynik.className = 'wynik-wyslania porazka';
      wynik.textContent = 'Zaznacz wymagane oświadczenie, bez niego zgłoszenie jest nieważne.';
    }

    if (bledy.length) {
      var pierwszy = document.querySelector('.ma-blad, .licznik-zdjec.za-malo');
      if (pierwszy) {
        pierwszy.scrollIntoView({ behavior: 'smooth', block: 'center' });
        var doPoprawy = pierwszy.querySelector('input, textarea');
        if (doPoprawy) doPoprawy.focus({ preventScroll: true });
      }
      if (!brakZgod) {
        wynik.className = 'wynik-wyslania porazka';
        wynik.textContent = 'Uzupełnij zaznaczone pola i spróbuj ponownie.';
      }
      return;
    }

    var dane = new FormData();
    ['imie_nazwisko', 'adres', 'telefon', 'email', 'adres_ogrodu', 'opis', 'strona_www'].forEach(function (n) {
      dane.append(n, form[n].value.trim());
    });
    dane.append('relacja', cudzy ? 'Zgłoszenie cudzego ogrodu za zgodą właściciela' : 'Własny ogród (właściciel lub użytkownik)');
    if (cudzy) {
      dane.append('wl_imie_nazwisko', form.wl_imie_nazwisko.value.trim());
      dane.append('wl_adres_ogrodu', form.wl_adres_ogrodu.value.trim());
      dane.append('wl_telefon', form.wl_telefon.value.trim());
      dane.append('zgoda_wlasciciela', form.zgoda_wlasciciela.files[0]);
    }
    zdjecia.forEach(function (z) { dane.append('zdjecia', z.plik, z.nazwa); });

    wyslijGuzik.disabled = true;
    wyslijGuzik.textContent = 'Wysyłamy zgłoszenie…';
    pasek.style.display = 'block';

    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/zgloszenie');
    xhr.timeout = 180000;
    xhr.upload.onprogress = function (ev) {
      if (ev.lengthComputable) pasekWypelnienie.style.width = Math.round(100 * ev.loaded / ev.total) + '%';
    };
    xhr.onload = function () {
      var ok = false, odp = {};
      try { odp = JSON.parse(xhr.responseText); ok = xhr.status === 200 && odp.ok; } catch (err) { /* nie-JSON */ }
      koniec(ok, odp.blad);
    };
    xhr.onerror = function () { koniec(false); };
    xhr.ontimeout = function () { koniec(false, 'Wysyłka trwała zbyt długo. Sprawdź zasięg i spróbuj ponownie.'); };
    xhr.send(dane);

    function koniec(ok, blad) {
      pasek.style.display = 'none';
      pasekWypelnienie.style.width = '0%';
      wyslijGuzik.disabled = false;
      wyslijGuzik.textContent = 'Wyślij zgłoszenie';
      if (ok) {
        slad('zgloszenie-konkursowe');
        wynik.className = 'wynik-wyslania sukces';
        wynik.textContent = 'Dziękujemy! Zgłoszenie dotarło do organizatorów. Komisja skontaktuje się telefonicznie, aby umówić wizytę w ogrodzie.';
        form.reset();
        zdjecia.forEach(function (z) { URL.revokeObjectURL(z.url); });
        zdjecia = [];
        rysujMiniatury();
        sekcjaB.classList.remove('widoczna');
        wynik.scrollIntoView({ behavior: 'smooth', block: 'center' });
      } else {
        wynik.className = 'wynik-wyslania porazka';
        wynik.textContent = blad || 'Nie udało się wysłać zgłoszenia. Spróbuj ponownie albo wyślij kartę e-mailem na kgw.czemierniki@gmail.com, ewentualnie zadzwoń: 795 716 644.';
        wynik.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  });
})();
