/* Klub Pasjonatów Ogrodnictwa Czemierniki: nawigacja, odsłanianie, galeria, formularz. */
(function () {
  'use strict';

  /* ---------- Menu mobilne ---------- */
  var guzik = document.querySelector('.menu-guzik');
  var menu = document.getElementById('menu');
  if (guzik && menu) {
    guzik.addEventListener('click', function () {
      var otwarte = menu.classList.toggle('otwarte');
      guzik.setAttribute('aria-expanded', otwarte ? 'true' : 'false');
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

  /* ---------- Galeria: podgląd w dialogu ---------- */
  var galeria = document.getElementById('galeria');
  if (galeria) {
    var dialog = document.createElement('dialog');
    dialog.className = 'podglad';
    dialog.innerHTML = '<button type="button" aria-label="Zamknij">×</button><img alt="">';
    document.body.appendChild(dialog);
    var duze = dialog.querySelector('img');
    galeria.addEventListener('click', function (e) {
      var a = e.target.closest('a');
      if (!a) return;
      e.preventDefault();
      duze.src = a.href;
      duze.alt = (a.querySelector('img') || {}).alt || '';
      dialog.showModal();
    });
    dialog.addEventListener('click', function (e) {
      if (e.target === dialog || e.target.tagName === 'BUTTON') dialog.close();
    });
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
      if (!poprawny) return;
      var guzik = fm.querySelector('button[type="submit"]');
      guzik.disabled = true;
      fetch('/api/kontakt', { method: 'POST', body: new FormData(fm) })
        .then(function (r) { return r.json(); })
        .then(function (odp) {
          if (!odp.ok) { var e2 = new Error(''); e2.wlasny = odp.blad; throw e2; }
          wynikMini.className = 'wynik-wyslania sukces';
          wynikMini.textContent = fm.getAttribute('data-sukces');
          fm.reset();
        })
        .catch(function (err) {
          wynikMini.className = 'wynik-wyslania porazka';
          wynikMini.textContent = (err && err.wlasny) ||
            'Nie udało się wysłać wiadomości. Zadzwoń: 795 716 644 albo napisz na kgw.czemierniki@gmail.com.';
        })
        .finally(function () { guzik.disabled = false; });
    });
  });

  /* ---------- Formularz konkursowy ---------- */
  var form = document.getElementById('formularz-konkursu');
  if (!form) return;

  var MIN_ZDJEC = 4, MAX_ZDJEC = 7, MAKS_BOK = 2000, JAKOSC = 0.85;
  var zdjecia = []; // { plik: Blob, nazwa: string, url: string }

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
    Array.prototype.slice.call(lista).forEach(function (plik) {
      if (!/^image\//.test(plik.type)) return;
      if (zdjecia.length >= MAX_ZDJEC) return;
      zmniejsz(plik).then(function (blob) {
        var url = URL.createObjectURL(blob);
        zdjecia.push({ plik: blob, nazwa: plik.name.replace(/\.\w+$/, '') + '.jpg', url: url });
        rysujMiniatury();
      });
    });
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
        URL.revokeObjectURL(z.url); zdjecia.splice(i, 1); rysujMiniatury();
      });
      fig.appendChild(img); fig.appendChild(usun); miniatury.appendChild(fig);
    });
    var n = zdjecia.length;
    var slowo = (n === 1) ? 'zdjęcie' : (n >= 2 && n <= 4) ? 'zdjęcia' : 'zdjęć';
    licznik.textContent = n < MIN_ZDJEC
      ? 'Dodano ' + n + ' z wymaganych 4–7 zdjęć.'
      : 'Dodano ' + n + ' ' + slowo + '. W porządku!' + (n < MAX_ZDJEC ? ' Możesz dodać jeszcze ' + (MAX_ZDJEC - n) + '.' : '');
    licznik.className = 'licznik-zdjec ' + (n >= MIN_ZDJEC ? 'ok' : 'za-malo');
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

    var zgody = form.querySelectorAll('.zgody input[type="checkbox"]');
    var brakZgod = Array.prototype.some.call(zgody, function (z) { return !z.checked; });
    if (brakZgod) {
      bledy.push('zgody');
      wynik.className = 'wynik-wyslania porazka';
      wynik.textContent = 'Zaznacz wszystkie oświadczenia, bez nich zgłoszenie jest nieważne.';
    }

    if (bledy.length) {
      var pierwszy = document.querySelector('.ma-blad, .licznik-zdjec.za-malo');
      if (pierwszy) pierwszy.scrollIntoView({ behavior: 'smooth', block: 'center' });
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
      }
    }
  });
})();
