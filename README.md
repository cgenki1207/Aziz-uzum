# Uzum tovar kuzatuvi

Uzum Market sotuvchilari uchun: Uzumga topshirilgan har bir dona tovar qayerda ekanini
hisoblab turadi va yo'qolgan yoki turib qolgan tovarlarni ko'rsatadi.

- **Qaytmagan tovarlar** — xaridor olmagan/qaytargan, lekin sizga qaytarish yuk xati bilan qaytmagan.
- **Qabulda sanalmagan** — siz topshirgan, lekin Uzum yuk xatida qabul qilmagan.
- **Uzumda yo'lda / punktda turib qolgan** — muddatidan uzoq harakatsiz turgan buyurtmalar.
- **Tovarlar balansi** — har bir SKU bo'yicha: qabul qilingan = sotilgan + yo'lda + punktda + qaytishi kerak.

Dastur Uzumda hech narsani o'zgartirmaydi — faqat o'qiydi. Hamma ma'lumot va API kaliti
faqat sizning kompyuteringizda (yoki o'zingizning Google Cloud serveringizda) saqlanadi.

## O'rnatish

### Mac

1. **Terminal** dasturini oching (Cmd+Probel bosib, `Terminal` deb yozing).
2. Quyidagi qatordan nusxa olib, Terminalga qo'ying va Enter bosing:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/cgenki1207/Aziz-uzum/main/install.sh | bash
   ```

3. Brauzerda panel ochiladi. Uzum Seller API kalitingizni kiriting
   (seller.uzum.uz → Sozlamalar → API kalitlari). Birinchi yuklash 1–2 daqiqa oladi.

Keyingi safar ish stolidagi **«Uzum Tracker»** belgisini ikki marta bosing.

Agar «Python topilmadi» desa: <https://www.python.org/downloads/> dan o'rnatib, 2-qadamni takrorlang.

> ZIP yuklab, faylni ikki marta bosish Mac'da ishlamaydi: macOS internetdan kelgan,
> Apple'da ro'yxatdan o'tmagan dasturlarni bloklaydi. Shuning uchun yuqoridagi usuldan foydalaning.

### Windows

1. **Python o'rnating** (bir marta): <https://www.python.org/downloads/>
   O'rnatish oynasida **«Add Python to PATH»** belgisini qo'ying.
2. Dasturni yuklab oling: **[ZIP yuklab olish](https://github.com/cgenki1207/Aziz-uzum/archive/refs/heads/main.zip)** va arxivni oching.
3. `Uzum Tracker.bat` faylini ikki marta bosing.
   («Windows protected your PC» chiqsa: **More info → Run anyway**.)
4. Brauzerda panel ochiladi, API kalitingizni kiriting.

Mac'da dastur orqa fonda ishlaydi: Terminal oynasini yopsangiz ham to'xtamaydi.
To'xtatish uchun paneldagi **«To'xtatish»** tugmasini bosing.
Windows'da qora oyna ochiq turishi kerak — uni yopsangiz dastur to'xtaydi.

Agar panelda «Dastur ishlamayapti» chiqsa — dastur yopilgan. «Uzum Tracker» ni qayta oching.

## Internetga joylash (Google Cloud, bepul)

Panelni kompyuter yoqilmagan paytda ham telefon yoki boshqa joydan ochish uchun uni
Google Cloud Run'ga joylash mumkin. Bepul limit ichida ishlaydi va panel parol bilan himoyalangan.

1. <https://console.cloud.google.com> ga Google hisobingiz bilan kiring va bepul sinovni faollashtiring
   (karta so'raladi, lekin bepul limitdan oshmasa pul yechilmaydi).
2. Yuqori o'ng burchakdagi **Cloud Shell** belgisini (`>_`) bosing.
3. Pastda ochilgan oynaga quyidagini qo'yib, Enter bosing:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/cgenki1207/Aziz-uzum/main/deploy-gcp.sh | bash
   ```

4. Skript Uzum API kalitini va panel uchun yangi parolni so'raydi (yozganda ekranda ko'rinmaydi).
   Oxirida panel manzili chiqadi (`https://uzum-tracker-….run.app`).

Shuni bilib qo'ying:

- Hech kim kirmasa server uxlaydi. Keyingi ochilishda Uzumdan ma'lumot qaytadan yuklanadi (2–3 daqiqa).
- Ma'lumotlar faqat panel ochiq paytda yangilanadi.
- Yangi versiya server uyg'onganda o'zi olinadi. Kalit yoki parolni almashtirish uchun 3-qadamni takrorlang.
- Skript $1 lik byudjet ogohlantirishini qo'yadi: Google pul yecha boshlasa, emailingizga xabar keladi.

## Yangilanish

Dastur har ochilganda yangi versiyani o'zi tekshiradi va o'zi yangilanadi.
Dastur ochiq turgan bo'lsa, panelda «Hozir yangilash» tugmasi chiqadi. Panel tepasida hozirgi versiya raqami ko'rinadi.

## Sozlamalar

Ma'lumotlar `~/.uzum-tracker/` papkasida (Windows: `C:\Users\<ism>\.uzum-tracker\`):

- `config.json` — API kaliti va sozlamalar
- `uzum.db` — yuklangan ma'lumotlar

`config.json` ga qo'shish mumkin bo'lgan sozlamalar:

| Kalit | Standart | Ma'nosi |
|---|---|---|
| `transit_days` | 7 | Uzumda yo'lda necha kundan keyin «turib qolgan» |
| `pickup_days` | 10 | Punktda necha kundan keyin «turib qolgan» |
| `return_days` | 14 | Necha kundan keyin qaytmagan tovar «yo'qolgan» |
| `sync_interval_min` | 30 | Har necha daqiqada Uzumdan yangilansin |
| `port` | 4000 | Panel porti |

API kalitini almashtirish: paneldagi **«API kaliti»** tugmasi.

## Namuna rejimi

API kalitisiz ko'rib chiqish uchun: `python3 run.py demo`
