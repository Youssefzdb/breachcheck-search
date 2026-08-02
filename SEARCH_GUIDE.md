# BreachCheck Tor Search — Setup Guide

## المتطلبات

### 1. تثبيت Tor
```bash
# Linux
sudo apt install tor
sudo systemctl start tor

# أو macOS
brew install tor
brew services start tor

# Windows: حمّل Tor Expert Bundle من https://www.torproject.org/download/
```

### 2. إعداد Tor لـ Stream Isolation (IP مختلف لكل worker)
أضف هذه الأسطر لملف `/etc/tor/torrc` (أو `torrc` على ويندوز):
```
SocksPort 9050 IsolateSOCKSAuth
ControlPort 9051
CookieAuthentication 1
```
أعد تشغيل Tor:
```bash
sudo systemctl restart tor
```

### 3. تثبيت Python dependencies
```bash
pip install requests pysocks dissect
```

## الاستخدام

### بحث بسيط (يتوقف عند أول نتيجة)
```bash
python3 search_tor.py user@example.com
```

### بحث شامل (يفحص كل الملفات)
```bash
python3 search_tor.py user@example.com --full
```

### تخصيص عدد الـ workers
```bash
python3 search_tor.py user@example.com --workers 30
```

### استخدام منفذ Tor مختلف
```bash
python3 search_tor.py user@example.com --tor-port 9051
```

### نتيجة JSON
```bash
python3 search_tor.py user@example.com --full --json > results.json
```

## كيف يعمل

1. يفتح SquashFS (280GB) من Internet Archive عبر HTTP Range — لا يحمل الملف كاملاً
2. كل worker thread يفتح Tor circuit مستقل (IP + UserAgent مختلف)
3. يبحثون في الملفات بالتوازي
4. النتائج تتجمّع مع dedup أوتوماتيكي (نفس email + password = نتيجة واحدة)
5. كل نتيجة تعرض: الإيميل، كلمة السر، اسم التسريب

## الميزات

- ✅ كل worker له IP مختلف (عبر Tor stream isolation)
- ✅ UserAgent متغير لكل طلب
- ✅ بحث متوازي (20 worker افتراضياً)
- ✅ Dedup أوتوماتيكي (email + password)
- ✅ لا يحمل 280GB — يقرأ فقط ما يحتاجه
- ✅ إيقاف عند أول نتيجة (اختياري) أو بحث شامل
- ✅ Progress reporting مع ETA

## ملاحظات

- سرعة البحث تعتمد على عدد الـ workers وسرعة Tor
- مع 20 worker: ~30-60 دقيقة للبحث الكامل
- مع 50 worker: ~15-30 دقيقة (يتطلب Tor قوي)
- كل worker يفتح SquashFS مستقل (يقرأ metadata مرة واحدة)
- الـ cache يحتفظ بآخر 300 block (1.2GB) لكل worker
