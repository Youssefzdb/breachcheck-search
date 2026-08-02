# 📡 Base44 Builder API — Complete Guide

## كيفية إرسال رسائل للبويلدر والتحقق منها

---

## الأدوات المستخدمة

| الأداة | الوظيفة | القيود |
|--------|---------|--------|
| `send_message_to_builder` | إرسال تعليمات للبويلدر لتعديل التطبيق | Rate limited: ~5 رسائل/دقيقة |
| `get_base44_app_status` | التحقق من حالة البويلدر (processing/ready/error) | لا قيود |
| `call_base44_backend_function` | استدعاء backend function بعد نشرها | Rate limited: ~20/دقيقة |
| `list_base44_apps` | عرض كل تطبيقات المستخدم | لا قيود |

---

## الخطوات الكاملة

### 1️⃣ الحصول على App ID

```python
# أولاً: عرض كل التطبيقات
apps = list_base44_apps()

# النتيجة:
# [
#   {"name": "BreachCheck", "id": "6a6e47497b4dab251c809a19", "status": "ready"},
#   {"name": "Solan", "id": "6a6e638e900e29de25c12473", "status": "ready"},
#   ...
# ]
```

### 2️⃣ إرسال رسالة للبويلدر

```python
# إرسال تعليمات للبويلدر
result = send_message_to_builder(
    app_id="6a6e47497b4dab251c809a19",
    message="Add a backend function called searchBreach that searches LeakedUsers by email"
)

# النتيجة الفورية:
# {
#   "app_id": "6a6e47497b4dab251c809a19",
#   "status": "processing",          ← البويلبد بدأ العمل
#   "editor_url": "https://app.base44.com/apps/.../editor/preview",
#   "note": "Builder message sent. Use get_base44_app_status to check progress."
# }
```

### 3️⃣ التحقق من حالة البويلدر

```python
# فحص الحالة — كرر كل 10-15 ثانية حتى تصبح "ready"
status = get_base44_app_status(app_id="6a6e47497b4dab251c809a19")

# أثناء المعالجة:
# {"status": "processing", "name": "BreachCheck", ...}

# بعد الانتهاء:
# {"status": "ready", "name": "BreachCheck", ...}

# في حالة الخطأ:
# {"status": "error", "error_source": "...", ...}
```

### 4️⃣ استدعاء الـ Backend Function بعد النشر

```python
# استدعاء الفنكشن التي أنشأها البويلدر
response = call_base44_backend_function(
    app_id="6a6e47497b4dab251c809a19",
    function_name="searchBreach",
    method="POST",
    payload={"email": "user@example.com"}
)

# النتيجة:
# {
#   "status_code": 200,
#   "elapsed_ms": 101,
#   "body": "{\"email\": \"user@example.com\", \"found\": true, ...}"
# }
```

---

## دورة الحياة الكاملة (Flow)

```
┌─────────────────────────────────────────────────────────────┐
│  1. list_base44_apps()                                       │
│     → الحصول على app_id                                       │
│                        ↓                                      │
│  2. send_message_to_builder(app_id, message)                 │
│     → إرسال التعليمات للبويلدر                                 │
│     → returns: status="processing"                           │
│                        ↓                                      │
│  3. get_base44_app_status(app_id)  ← كرر كل 10-15 ثانية       │
│     → "processing" → انتظر                                     │
│     → "ready" → اكتمل                                          │
│     → "error" → راجع الرسالة                                   │
│                        ↓                                      │
│  4. call_base44_backend_function(app_id, function_name)      │
│     → استدعاء الفنكشن والتأكد من النتيجة                       │
│     → status_code=200 = نجح                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## أمثلة عملية

### مثال 1: إنشاء Backend Function للبحث

```python
# 1. إرسال الرسالة
send_message_to_builder(
    app_id="6a6e47497b4dab251c809a19",
    message="""
    Add a backend function called "searchBreach" with this code:
    
    export default async function(req, res) {
        const { email } = req.body || req.query;
        const results = await base44.entities.LeakedUsers.filter(
            { email: email.toLowerCase() },
            { limit: 100, fields: ["email", "password", "domain"] }
        );
        return res.json({ email, found: results.length > 0, count: results.length, results });
    }
    """
)

# 2. الانتظار والتحقق
import time
while True:
    status = get_base44_app_status(app_id="6a6e47497b4dab251c809a19")
    if status["status"] == "ready":
        break
    elif status["status"] == "error":
        print("Error:", status)
        break
    time.sleep(10)

# 3. استدعاء الفنكشن
result = call_base44_backend_function(
    app_id="6a6e47497b4dab251c809a19",
    function_name="searchBreach",
    payload={"email": "user@example.com"}
)
print(result)
```

### مثال 2: إضافة Entity جديد

```python
send_message_to_builder(
    app_id="6a6e47497b4dab251c809a19",
    message="Create a new entity called 'SearchLogs' with fields: query (string), results_count (number), timestamp (date), ip (string)"
)
```

### مثال 3: تعديل صفحة

```python
send_message_to_builder(
    app_id="6a6e47497b4dab251c809a19",
    message="On the search page, add a search input field and a results table. The search should call the searchBreach backend function."
)
```

---

## القيود والملاحظات

| القيد | التفاصيل |
|-------|----------|
| Rate limit | ~5 رسائل/دقيقة للبويلدر |
| Processing time | 10-30 ثانية عادةً |
| Backend function calls | ~20/دقيقة |
| لا retry | لا تعد إرسال بدون انتظار ready/error |
| وصول البويلدر | فقط الـ owner يستطيع الإرسال |
| Backend function access | حسب إعدادات التطبيق (public/auth) |

---

## الثغرة الأمنية المكتشفة

```
قراءة Entity مباشرة:
  read_entities(app_id="X", entity_name="Y")
  → أي أحد يعرف app_id + entity_name يقرأ كل البيانات
  → لا تحتاج مصادقة
  → تشمل كلمات السر والبيانات الحساسة

إرسال للبويلدر:
  send_message_to_builder(app_id="X", message="...")
  → فقط الـ owner يستطيع
  → آمن

استدعاء Backend Function:
  call_base44_backend_function(app_id="X", function_name="Y")
  → حسب إعدادات الفنكشن (public/protected)
  → ممكن يكون متاح للعموم
```

---

## 最佳实践

1. **لا ترسل رسالة ثانية** قبل ما تصبح الحالة `ready` أو `error`
2. **اكتب كود واضح** في الرسالة — البويلدر يفهم TypeScript/JavaScript
3. **اختبر بعد النشر** بـ `call_base44_backend_function`
4. **استخدم `fields`** في الـ entities لتقليل حجم البيانات
5. **فعّل RLS** على الـ entities الحساسة لمنع الوصول الخارجي
