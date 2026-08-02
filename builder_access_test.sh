#!/bin/bash
# ============================================
# Base44 Builder API — External Access Test
# الهدف: هل أي شخص يقدر يوصل للبويلدر؟
# ============================================

APP_ID="6a6e47497b4dab251c809a19"
AGENT_ID="6a6e638e900e29de25c12473"
BASE="https://app.base44.com"

echo "============================================"
echo "  Base44 Builder API Access Test"
echo "  App: BreachCheck ($APP_ID)"
echo "============================================"

# ============================================
# TEST 1: محاولة إرسال رسالة للبويلدر بدون أي auth
# مسارات محتملة للـ builder
# ============================================
echo ""
echo "=== [1] Builder — بدون مصادقة ==="

ENDPOINTS=(
  "/api/apps/$APP_ID/builder-message"
  "/api/apps/$APP_ID/builder"
  "/api/apps/$APP_ID/edit"
  "/api/apps/$APP_ID/messages"
  "/api/apps/$APP_ID/prompt"
  "/api/builder/apps/$APP_ID/message"
  "/api/apps/$APP_ID/editor/message"
)

for ep in "${ENDPOINTS[@]}"; do
  echo ""
  echo "POST $BASE$ep"
  curl -s -o /dev/null -X POST "$BASE$ep" \
    -H "Content-Type: application/json" \
    -d '{"message":"Add a test function called hacktest"}' \
    -w "  HTTP Status: %{http_code} | Size: %{size_download} bytes\n" \
    --connect-timeout 10 --max-time 15
done

# ============================================
# TEST 2: محاولة قراءة حالة التطبيق بدون auth
# ============================================
echo ""
echo "=== [2] App Status — بدون مصادقة ==="

STATUS_ENDPOINTS=(
  "/api/apps/$APP_ID/status"
  "/api/apps/$APP_ID"
  "/api/apps/$APP_ID/details"
)

for ep in "${STATUS_ENDPOINTS[@]}"; do
  echo ""
  echo "GET $BASE$ep"
  curl -s -X GET "$BASE$ep" \
    -w "\n  HTTP Status: %{http_code} | Size: %{size_download} bytes\n" \
    --connect-timeout 10 --max-time 15 2>&1 | head -5
done

# ============================================
# TEST 3: محاولة قراءة entities بدون auth
# ============================================
echo ""
echo "=== [3] Read Entities — بدون مصادقة ==="

ENTITY_ENDPOINTS=(
  "/api/apps/$APP_ID/entities/LeakedUsers?limit=3"
  "/api/apps/$APP_ID/entities/LeakedUsers/records?limit=3"
  "/api/entities/LeakedUsers?limit=3&app_id=$APP_ID"
)

for ep in "${ENTITY_ENDPOINTS[@]}"; do
  echo ""
  echo "GET $BASE$ep"
  curl -s -X GET "$BASE$ep" \
    -w "\n  HTTP Status: %{http_code} | Size: %{size_download} bytes\n" \
    --connect-timeout 10 --max-time 15 2>&1 | head -5
done

# ============================================
# TEST 4: محاولة مع Agent API (لو عندك API key)
# ============================================
echo ""
echo "=== [4] Agent API — التواصل مع السوبراجنت ==="
echo "  (يحتاج API key من Base44 Editor > Developer > API Docs)"
echo ""
echo "  لو عندك API key، نفذ:"
echo ""
echo '  curl -s -X POST "'$BASE'/api/agents/'$AGENT_ID'/conversations/default/messages" \'
echo '    -H "Content-Type: application/json" \'
echo '    -H "api_key: YOUR_API_KEY_HERE" \'
echo '    -d "{\"message\": \"Add a test function to BreachCheck\"}"'
echo ""

# ============================================
# TEST 5: محاولة استدعاء backend function (public)
# ============================================
echo "=== [5] Backend Function — بدون مصادقة ==="
echo ""
echo "POST $BASE/api/apps/$APP_ID/backend-functions/searchBreach"
curl -s -X POST "$BASE/api/apps/$APP_ID/backend-functions/searchBreach" \
  -H "Content-Type: application/json" \
  -d '{"email":"khow44@voila.fr"}' \
  -w "\n  HTTP Status: %{http_code}\n" \
  --connect-timeout 10 --max-time 15 2>&1 | head -20

# ============================================
# TEST 6: تجربة مع Bearer token وهمي
# ============================================
echo ""
echo "=== [6] Builder — Bearer token وهمي ==="
curl -s -o /dev/null -X POST "$BASE/api/apps/$APP_ID/builder-message" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer FAKE_TOKEN_12345" \
  -d '{"message":"test"}' \
  -w "  HTTP Status: %{http_code} | Size: %{size_download} bytes\n" \
  --connect-timeout 10 --max-time 15

# ============================================
# النتيجة المتوقعة:
# ============================================
echo ""
echo "============================================"
echo "  توقع النتائج:"
echo "============================================"
echo "  200 = الوصول مفتوح (ثغرة!)"
echo "  401 = محتاج مصادقة (آمن)"
echo "  403 = ممنوع (آمن)"
echo "  404 = المسار غير موجود"
echo "  405 = method غير مسموح (جرّب GET/POST)"
echo "============================================"
echo ""
echo "  لو TEST 5 رجع 200 = الـ backend function عامة"
echo "  لو باقي الـ tests رجعت 401/403/404 = البويلدر محمي"
echo "============================================"
