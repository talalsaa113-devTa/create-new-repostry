import json
import os
from datetime import datetime

import yfinance as yf

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# ============================================================
# الإعدادات
# ============================================================

TOKEN = os.getenv("TOKEN")
ALERTS_FILE = "alerts.json"


# ============================================================
# التنبيهات
# ============================================================

def load_alerts():
    if not os.path.exists(ALERTS_FILE):
        return {}

    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def save_alerts(alerts):
    with open(ALERTS_FILE, "w", encoding="utf-8") as file:
        json.dump(alerts, file, ensure_ascii=False, indent=2)


# ============================================================
# RSI
# ============================================================

def calculate_rsi(close, period=14):
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


# ============================================================
# MACD
# ============================================================

def calculate_macd(close):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()

    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()

    return macd, signal


# ============================================================
# الدعم والمقاومة
# ============================================================

def get_support_resistance(data, price):
    """
    استخراج مستويات الدعم والمقاومة من القمم والقيعان المحلية.
    """

    highs = data["High"]
    lows = data["Low"]

    supports = []
    resistances = []

    # نستخدم آخر 90 يوم كحد أقصى
    recent = data.tail(90)

    high_values = recent["High"].tolist()
    low_values = recent["Low"].tolist()

    for i in range(2, len(recent) - 2):

        # قمة محلية
        if (
            high_values[i] > high_values[i - 1]
            and high_values[i] > high_values[i - 2]
            and high_values[i] > high_values[i + 1]
            and high_values[i] > high_values[i + 2]
        ):
            level = float(high_values[i])

            if level > price:
                resistances.append(level)

        # قاع محلي
        if (
            low_values[i] < low_values[i - 1]
            and low_values[i] < low_values[i - 2]
            and low_values[i] < low_values[i + 1]
            and low_values[i] < low_values[i + 2]
        ):
            level = float(low_values[i])

            if level < price:
                supports.append(level)

    # إضافة أعلى/أدنى 30 يوم كمرجع إضافي
    high30 = float(recent["High"].tail(30).max())
    low30 = float(recent["Low"].tail(30).min())

    if high30 > price:
        resistances.append(high30)

    if low30 < price:
        supports.append(low30)

    # إزالة المستويات المتقاربة جدًا
    def clean_levels(levels):
        levels = sorted(levels)

        result = []

        for level in levels:
            if not result:
                result.append(level)
                continue

            # تجاهل المستويات التي تبعد أقل من 0.7%
            difference = abs(level - result[-1]) / result[-1]

            if difference >= 0.007:
                result.append(level)

        return result

    supports = clean_levels(supports)
    resistances = clean_levels(resistances)

    # أقرب 3 مستويات
    supports = sorted(
        supports,
        key=lambda x: abs(price - x)
    )[:3]

    resistances = sorted(
        resistances,
        key=lambda x: abs(x - price)
    )[:3]

    supports = sorted(supports, reverse=True)
    resistances = sorted(resistances)

    return supports, resistances


# ============================================================
# الخيارات
# ============================================================

def get_options(symbol, price, supports, resistances):
    """
    البحث عن عقود Call و Put مناسبة نسبيًا.
    لا يوجد عقد خالي من المخاطر.
    """

    try:
        stock = yf.Ticker(symbol)

        expirations = stock.options

        if not expirations:
            return "❌ لا توجد بيانات خيارات متاحة حاليًا."

        # اختيار أقرب تاريخ بعد 14 يوم تقريبًا
        today = datetime.now().date()

        selected_expiry = None

        for expiry in expirations:
            try:
                expiry_date = datetime.strptime(
                    expiry,
                    "%Y-%m-%d"
                ).date()

                days = (expiry_date - today).days

                if 14 <= days <= 60:
                    selected_expiry = expiry
                    break

            except Exception:
                continue

        # إذا لم نجد تاريخًا مناسبًا
        if selected_expiry is None:
            selected_expiry = expirations[0]

        chain = stock.option_chain(selected_expiry)

        calls = chain.calls
        puts = chain.puts

        if calls.empty and puts.empty:
            return "❌ لا توجد عقود متاحة."

        # ====================================================
        # اختيار Call
        # ====================================================

        call_candidates = []

        for _, row in calls.iterrows():

            strike = float(row["strike"])

            if strike < price:
                continue

            bid = row.get("bid", 0)
            ask = row.get("ask", 0)
            volume = row.get("volume", 0)
            oi = row.get("openInterest", 0)
            iv = row.get("impliedVolatility", 0)

            try:
                bid = float(bid)
            except Exception:
                bid = 0

            try:
                ask = float(ask)
            except Exception:
                ask = 0

            try:
                volume = int(volume) if volume else 0
            except Exception:
                volume = 0

            try:
                oi = int(oi) if oi else 0
            except Exception:
                oi = 0

            try:
                iv = float(iv)
            except Exception:
                iv = 0

            if ask <= 0:
                continue

            # السبريد
            spread = 0

            if ask > 0 and bid >= 0:
                spread = (ask - bid) / ask

            distance = abs(strike - price) / price

            # نفضل:
            # - Strike قريب من السعر
            # - OI عالي
            # - Volume عالي
            # - Spread صغير
            score = 0

            if distance <= 0.06:
                score += 3

            if distance <= 0.03:
                score += 2

            if oi >= 1000:
                score += 2

            if volume >= 100:
                score += 2

            if spread <= 0.10:
                score += 2

            # إذا كان الـStrike قريب من المقاومة القادمة
            if resistances:
                nearest_resistance = resistances[0]

                resistance_distance = abs(
                    strike - nearest_resistance
                ) / price

                if resistance_distance <= 0.04:
                    score += 2

            call_candidates.append({
                "strike": strike,
                "bid": bid,
                "ask": ask,
                "volume": volume,
                "oi": oi,
                "iv": iv,
                "spread": spread,
                "score": score
            })

        # ====================================================
        # اختيار Put
        # ====================================================

        put_candidates = []

        for _, row in puts.iterrows():

            strike = float(row["strike"])

            if strike > price:
                continue

            bid = row.get("bid", 0)
            ask = row.get("ask", 0)
            volume = row.get("volume", 0)
            oi = row.get("openInterest", 0)
            iv = row.get("impliedVolatility", 0)

            try:
                bid = float(bid)
            except Exception:
                bid = 0

            try:
                ask = float(ask)
            except Exception:
                ask = 0

            try:
                volume = int(volume) if volume else 0
            except Exception:
                volume = 0

            try:
                oi = int(oi) if oi else 0
            except Exception:
                oi = 0

            try:
                iv = float(iv)
            except Exception:
                iv = 0

            if ask <= 0:
                continue

            spread = 0

            if ask > 0 and bid >= 0:
                spread = (ask - bid) / ask

            distance = abs(strike - price) / price

            score = 0

            if distance <= 0.06:
                score += 3

            if distance <= 0.03:
                score += 2

            if oi >= 1000:
                score += 2

            if volume >= 100:
                score += 2

            if spread <= 0.10:
                score += 2

            # إذا كان الـStrike قريب من الدعم القادم
            if supports:
                nearest_support = supports[0]

                support_distance = abs(
                    strike - nearest_support
                ) / price

                if support_distance <= 0.04:
                    score += 2

            put_candidates.append({
                "strike": strike,
                "bid": bid,
                "ask": ask,
                "volume": volume,
                "oi": oi,
                "iv": iv,
                "spread": spread,
                "score": score
            })

        call_candidates.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        put_candidates.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        text = f"""
📑 خيارات {symbol}

💰 السعر الحالي:
${price:.2f}

📅 الانتهاء:
{selected_expiry}

━━━━━━━━━━━━━━━━━━
"""

        # ====================================================
        # أفضل Call
        # ====================================================

        if call_candidates:

            call = call_candidates[0]

            premium = (
                (call["bid"] + call["ask"]) / 2
            )

            text += f"""
🟢 CALL المقترح نسبيًا

🎯 Strike:
${call["strike"]:.2f}

💵 Premium:
${premium:.2f}

📊 Bid / Ask:
${call["bid"]:.2f} / ${call["ask"]:.2f}

📦 Volume:
{call["volume"]:,}

📚 Open Interest:
{call["oi"]:,}

📈 IV:
{call["iv"] * 100:.1f}%

⭐ التقييم:
{call["score"]}/13
"""

        else:
            text += """
🟢 CALL
❌ لا يوجد عقد مناسب حاليًا.
"""

        # ====================================================
        # أفضل Put
        # ====================================================

        if put_candidates:

            put = put_candidates[0]

            premium = (
                (put["bid"] + put["ask"]) / 2
            )

            text += f"""

🔴 PUT المقترح نسبيًا

🎯 Strike:
${put["strike"]:.2f}

💵 Premium:
${premium:.2f}

📊 Bid / Ask:
${put["bid"]:.2f} / ${put["ask"]:.2f}

📦 Volume:
{put["volume"]:,}

📚 Open Interest:
{put["oi"]:,}

📈 IV:
{put["iv"] * 100:.1f}%

⭐ التقييم:
{put["score"]}/13
"""

        else:
            text += """
🔴 PUT
❌ لا يوجد عقد مناسب حاليًا.
"""

        text += """

━━━━━━━━━━━━━━━━━━

⚠️ "مقترح نسبيًا" لا يعني قليل المخاطر أو مضمون.
⚠️ المشتري يمكن أن يخسر كامل قيمة Premium.
"""

        return text

    except Exception as error:
        print("OPTIONS ERROR:", error)

        return """
❌ تعذر جلب بيانات الخيارات.

قد لا تكون بيانات Options متاحة لهذا السهم حاليًا.
"""


# ============================================================
# تحليل السهم
# ============================================================

def analyze_stock(symbol):
    symbol = symbol.upper().strip()

    try:
        data = yf.Ticker(symbol).history(
            period="6mo",
            interval="1d"
        )

        if data.empty or len(data) < 50:
            return None

        close = data["Close"]

        price = float(close.iloc[-1])
        previous = float(close.iloc[-2])

        change = (
            (price - previous)
            / previous
        ) * 100

        ma20 = float(
            close.rolling(20).mean().iloc[-1]
        )

        ma50 = float(
            close.rolling(50).mean().iloc[-1]
        )

        rsi = calculate_rsi(close)
        rsi_value = float(rsi.iloc[-1])

        macd, signal = calculate_macd(close)

        macd_value = float(macd.iloc[-1])
        signal_value = float(signal.iloc[-1])

        high30 = float(
            data["High"].tail(30).max()
        )

        low30 = float(
            data["Low"].tail(30).min()
        )

        # ====================================================
        # الدعم والمقاومة
        # ====================================================

        supports, resistances = get_support_resistance(
            data,
            price
        )

        if price > ma20 > ma50:
            trend = "🟢 صاعد"

        elif price < ma20 < ma50:
            trend = "🔴 هابط"

        else:
            trend = "🟡 متذبذب"

        if rsi_value < 30:
            rsi_status = "🟢 تشبع بيع"

        elif rsi_value > 70:
            rsi_status = "🔴 تشبع شراء"

        else:
            rsi_status = "⚪ طبيعي"

        if macd_value > signal_value:
            macd_status = "🟢 إيجابي"

        else:
            macd_status = "🔴 سلبي"

        score = 0

        if price > ma20:
            score += 1

        if ma20 > ma50:
            score += 1

        if macd_value > signal_value:
            score += 1

        if 30 <= rsi_value <= 70:
            score += 1

        if price > high30 * 0.97:
            score += 1

        if score >= 4:
            final_signal = "🟢 إيجابية"

        elif score <= 1:
            final_signal = "🔴 سلبية"

        else:
            final_signal = "🟡 محايدة"

        if change > 0:
            daily_change = f"🟢 +{change:.2f}%"

        elif change < 0:
            daily_change = f"🔴 {change:.2f}%"

        else:
            daily_change = "⚪ 0.00%"

        # ====================================================
        # الدعم
        # ====================================================

        if supports:

            support_text = ""

            for i, level in enumerate(
                supports,
                start=1
            ):
                distance = (
                    (level - price)
                    / price
                ) * 100

                support_text += (
                    f"{i}️⃣ ${level:.2f} "
                    f"({distance:.2f}%)\n"
                )

            nearest_support = supports[0]

        else:

            support_text = "❌ لا يوجد مستوى واضح.\n"
            nearest_support = None

        # ====================================================
        # المقاومة
        # ====================================================

        if resistances:

            resistance_text = ""

            for i, level in enumerate(
                resistances,
                start=1
            ):
                distance = (
                    (level - price)
                    / price
                ) * 100

                resistance_text += (
                    f"{i}️⃣ ${level:.2f} "
                    f"(+{distance:.2f}%)\n"
                )

            nearest_resistance = resistances[0]

        else:

            resistance_text = "❌ لا يوجد مستوى واضح.\n"
            nearest_resistance = None

        # ====================================================
        # السيناريو القادم
        # ====================================================

        if (
            nearest_resistance is not None
            and nearest_support is not None
        ):

            resistance_distance = (
                (
                    nearest_resistance
                    - price
                )
                / price
            ) * 100

            support_distance = (
                (
                    nearest_support
                    - price
                )
                / price
            ) * 100

            if trend == "🟢 صاعد":

                scenario = f"""
🟢 السيناريو الأقرب:

اختراق المقاومة
${nearest_resistance:.2f}

→ الهدف التالي:
${resistances[1]:.2f}
""" if len(resistances) > 1 else f"""
🟢 السيناريو الأقرب:

اختراق المقاومة
${nearest_resistance:.2f}

→ السهم قد يستهدف مستويات أعلى.
"""

            elif trend == "🔴 هابط":

                scenario = f"""
🔴 السيناريو الأقرب:

كسر الدعم
${nearest_support:.2f}

→ الهدف التالي:
${supports[1]:.2f}
""" if len(supports) > 1 else f"""
🔴 السيناريو الأقرب:

كسر الدعم
${nearest_support:.2f}

→ السهم قد يبحث عن دعم أدنى.
"""

            else:

                if resistance_distance < abs(
                    support_distance
                ):

                    scenario = f"""
🟡 السيناريو الأقرب:

المقاومة الأقرب:
${nearest_resistance:.2f}

الدعم:
${nearest_support:.2f}

راقب الاختراق أو الكسر قبل اتخاذ القرار.
"""

                else:

                    scenario = f"""
🟡 السيناريو الأقرب:

الدعم الأقرب:
${nearest_support:.2f}

المقاومة:
${nearest_resistance:.2f}

راقب الكسر أو الارتداد.
"""

        else:

            scenario = """
🟡 لا يوجد مستوى واضح كافٍ لتحديد
السيناريو القادم.
"""

        return f"""
📊 تحليل {symbol}

━━━━━━━━━━━━━━━━━━

💰 السعر:
${price:.2f}

📅 التغير:
{daily_change}

📈 الاتجاه:
{trend}

━━━━━━━━━━━━━━━━━━

📊 RSI:
{rsi_value:.1f}

الحالة:
{rsi_status}

📉 MACD:
{macd_status}

━━━━━━━━━━━━━━━━━━

📏 MA20:
${ma20:.2f}

📏 MA50:
${ma50:.2f}

━━━━━━━━━━━━━━━━━━

🛡️ الدعوم:

{support_text}

🚧 المقاومات:

{resistance_text}

━━━━━━━━━━━━━━━━━━

{scenario}

━━━━━━━━━━━━━━━━━━

🔔 الإشارة:
{final_signal}

⭐ القوة:
{score}/5

━━━━━━━━━━━━━━━━━━

⚠️ تحليل آلي وليس توصية مالية.
"""


# ============================================================
# الأرباح
# ============================================================

def get_earnings(symbol):
    symbol = symbol.upper().strip()

    try:
        stock = yf.Ticker(symbol)

        earnings_date = None

        try:
            calendar = stock.calendar

            if isinstance(calendar, dict):

                dates = calendar.get(
                    "Earnings Date"
                )

                if dates:
                    earnings_date = dates[0]

            else:

                if "Earnings Date" in calendar.index:

                    earnings_dates = calendar.loc[
                        "Earnings Date"
                    ]

                    if hasattr(
                        earnings_dates,
                        "iloc"
                    ):
                        earnings_date = (
                            earnings_dates.iloc[0]
                        )

                    else:
                        earnings_date = earnings_dates

        except Exception as error:
            print("CALENDAR ERROR:", error)

        text = f"""
💰 أرباح {symbol}

━━━━━━━━━━━━━━━━━━

📅 إعلان الأرباح القادم:
"""

        if earnings_date is not None:

            try:

                if hasattr(
                    earnings_date,
                    "strftime"
                ):

                    text += earnings_date.strftime(
                        "%Y-%m-%d"
                    )

                else:

                    text += str(
                        earnings_date
                    )[:10]

            except Exception:

                text += str(
                    earnings_date
                )[:10]

        else:

            text += "غير متوفر حاليًا"

        text += """

━━━━━━━━━━━━━━━━━━

📋 آخر 4 إعلانات:

"""

        try:
            earnings = stock.get_earnings_dates(
                limit=8
            )
        except Exception:
            earnings = None

        if earnings is None or earnings.empty:

            text += (
                "❌ لا توجد بيانات أرباح متاحة.\n"
            )

        else:

            rows = earnings.head(4)

            for index, row in rows.iterrows():

                actual = row.get(
                    "Reported EPS"
                )

                estimate = row.get(
                    "EPS Estimate"
                )

                surprise = row.get(
                    "Surprise(%)"
                )

                try:
                    actual_text = (
                        f"${float(actual):.2f}"
                    )
                except Exception:
                    actual_text = "غير متوفر"

                try:
                    estimate_text = (
                        f"${float(estimate):.2f}"
                    )
                except Exception:
                    estimate_text = "غير متوفر"

                try:

                    surprise_value = float(
                        surprise
                    )

                    if surprise_value > 0:
                        result = (
                            "🟢 تفوقت على التوقعات"
                        )

                    elif surprise_value < 0:
                        result = (
                            "🔴 أقل من التوقعات"
                        )

                    else:
                        result = (
                            "🟡 مطابقة للتوقعات"
                        )

                    surprise_text = (
                        f"{surprise_value:+.2f}%"
                    )

                except Exception:

                    result = "⚪ غير متوفر"
                    surprise_text = "غير متوفر"

                text += (
                    f"📅 {str(index)[:10]}\n"
                    f"💵 الفعلي: {actual_text}\n"
                    f"🎯 المتوقع: {estimate_text}\n"
                    f"📊 المفاجأة: {surprise_text}\n"
                    f"{result}\n\n"
                )

        text += """
━━━━━━━━━━━━━━━━━━

⚠️ البيانات تعتمد على توفر وتحديث
مصدر البيانات.
"""

        return text

    except Exception as error:

        print("EARNINGS ERROR:", error)

        return f"""
❌ تعذر جلب أرباح {symbol}.

تأكد من رمز السهم وحاول مرة أخرى.
"""


# ============================================================
# الأخبار
# ============================================================

def get_news(symbol):
    symbol = symbol.upper().strip()

    try:
        stock = yf.Ticker(symbol)

        news = stock.news

        if not news:

            return f"""
📰 أخبار {symbol}

❌ لم أجد أخبارًا متاحة حاليًا.
"""

        text = f"""
📰 آخر أخبار {symbol}

━━━━━━━━━━━━━━━━━━

"""

        count = 0

        for item in news:

            if count >= 5:
                break

            try:

                content = item.get(
                    "content",
                    {}
                )

                title = content.get(
                    "title"
                )

                if not title:
                    title = item.get(
                        "title"
                    )

                if not title:
                    continue

                provider = content.get(
                    "provider",
                    {}
                )

                if isinstance(
                    provider,
                    dict
                ):
                    publisher = provider.get(
                        "displayName"
                    )
                else:
                    publisher = None

                click_url = content.get(
                    "clickThroughUrl",
                    {}
                )

                if isinstance(
                    click_url,
                    dict
                ):
                    link = click_url.get(
                        "url"
                    )
                else:
                    link = None

                text += f"🗞️ {title}\n"

                if publisher:
                    text += (
                        f"🏢 المصدر: {publisher}\n"
                    )

                if link:
                    text += (
                        f"🔗 {link}\n"
                    )

                text += "\n"

                count += 1

            except Exception as error:
                print(
                    "NEWS ITEM ERROR:",
                    error
                )

        if count == 0:

            return f"""
📰 أخبار {symbol}

❌ لم أجد أخبارًا قابلة للعرض حاليًا.
"""

        text += """
━━━━━━━━━━━━━━━━━━

⚠️ الأخبار من مصادر خارجية.
"""

        return text

    except Exception as error:

        print(
            "NEWS ERROR:",
            error
        )

        return f"""
❌ تعذر جلب أخبار {symbol}.

تأكد من رمز السهم وحاول مرة أخرى.
"""


# ============================================================
# /start
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    keyboard = [
        ["📊 تحليل سهم", "📑 الخيارات"],
        ["💰 الأرباح", "📰 أخبار الشركة"],
        ["🔔 تنبيه", "📋 تنبيهاتي"],
        ["❓ المساعدة"],
    ]

    keyboard_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

    await update.message.reply_text(
        """
🤖 أهلاً بك في Stock Talal

📈 بوت تحليل وتنبيهات الأسهم

اختر الخدمة من الأزرار 👇

أو اكتب رمز السهم مباشرة مثل:

AAPL
TSLA
NVDA
""",
        reply_markup=keyboard_markup
    )


# ============================================================
# المساعدة
# ============================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        """
📚 طريقة الاستخدام

📊 تحليل:
AAPL

📑 خيارات:
 /o AAPL

💰 الأرباح:
/e AAPL

📰 الأخبار:
/news AAPL

🔔 تنبيه:
/alert AAPL 300

📋 تنبيهاتك:
/alerts

🗑️ حذف:
/remove AAPL
"""
    )


# ============================================================
# تحليل
# ============================================================

async def analyze_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "مثال:\n/analyze AAPL"
        )

        return

    symbol = context.args[0].upper()

    message = await update.message.reply_text(
        f"🔍 جاري تحليل {symbol}..."
    )

    result = analyze_stock(symbol)

    if result is None:

        await message.edit_text(
            f"❌ لم أجد بيانات لـ {symbol}."
        )

        return

    await message.edit_text(result)


# ============================================================
# الخيارات /o
# ============================================================

async def options_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "مثال:\n/o AAPL"
        )

        return

    symbol = context.args[0].upper()

    message = await update.message.reply_text(
        f"📑 جاري تحليل خيارات {symbol}..."
    )

    try:

        data = yf.Ticker(symbol).history(
            period="6mo",
            interval="1d"
        )

        if data.empty:

            await message.edit_text(
                f"❌ لا توجد بيانات لـ {symbol}."
            )

            return

        price = float(
            data["Close"].iloc[-1]
        )

        supports, resistances = (
            get_support_resistance(
                data,
                price
            )
        )

        result = get_options(
            symbol,
            price,
            supports,
            resistances
        )

        await message.edit_text(
            result
        )

    except Exception as error:

        print(
            "OPTIONS COMMAND ERROR:",
            error
        )

        await message.edit_text(
            "❌ تعذر جلب بيانات الخيارات."
        )


# ============================================================
# الأرباح المختصر
# ============================================================

async def earnings_shortcut(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    parts = update.message.text.split()

    if len(parts) != 2:

        await update.message.reply_text(
            "اكتب:\ne AAPL"
        )

        return

    symbol = parts[1].upper()

    message = await update.message.reply_text(
        f"🔍 جاري جلب أرباح {symbol}..."
    )

    result = get_earnings(symbol)

    await message.edit_text(result)


# ============================================================
# /e
# ============================================================

async def earnings_short_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "مثال:\n/e AAPL"
        )

        return

    symbol = context.args[0].upper()

    message = await update.message.reply_text(
        f"🔍 جاري جلب أرباح {symbol}..."
    )

    result = get_earnings(symbol)

    await message.edit_text(result)


# ============================================================
# /earnings
# ============================================================

async def earnings_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "مثال:\n/earnings AAPL"
        )

        return

    symbol = context.args[0].upper()

    message = await update.message.reply_text(
        f"🔍 جاري جلب أرباح {symbol}..."
    )

    result = get_earnings(symbol)

    await message.edit_text(result)


# ============================================================
# /news
# ============================================================

async def news_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "مثال:\n/news AAPL"
        )

        return

    symbol = context.args[0].upper()

    message = await update.message.reply_text(
        f"📰 جاري جلب أخبار {symbol}..."
    )

    result = get_news(symbol)

    await message.edit_text(
        result,
        disable_web_page_preview=True
    )


# ============================================================
# إضافة تنبيه
# ============================================================

async def alert_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if len(context.args) != 2:

        await update.message.reply_text(
            "مثال:\n/alert AAPL 300"
        )

        return

    symbol = context.args[0].upper()

    try:
        target = float(
            context.args[1]
        )

    except Exception:

        await update.message.reply_text(
            "❌ السعر غير صحيح."
        )

        return

    chat_id = str(
        update.effective_chat.id
    )

    alerts = load_alerts()

    if chat_id not in alerts:
        alerts[chat_id] = {}

    alerts[chat_id][symbol] = {
        "target": target
    }

    save_alerts(alerts)

    await update.message.reply_text(
        f"""
🔔 تم إنشاء التنبيه

📊 السهم:
{symbol}

🎯 السعر:
${target:.2f}

سأراقبه لك.
"""
    )


# ============================================================
# عرض التنبيهات
# ============================================================

async def alerts_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    chat_id = str(
        update.effective_chat.id
    )

    alerts = load_alerts()

    user_alerts = alerts.get(
        chat_id,
        {}
    )

    if not user_alerts:

        await update.message.reply_text(
            "📭 لا توجد لديك تنبيهات."
        )

        return

    text = "🔔 تنبيهاتك:\n\n"

    for symbol, info in user_alerts.items():

        text += (
            f"📊 {symbol}\n"
            f"🎯 ${info['target']:.2f}\n\n"
        )

    await update.message.reply_text(text)


# ============================================================
# حذف تنبيه
# ============================================================

async def remove_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "مثال:\n/remove AAPL"
        )

        return

    symbol = context.args[0].upper()

    chat_id = str(
        update.effective_chat.id
    )

    alerts = load_alerts()

    if (
        chat_id not in alerts
        or symbol not in alerts[chat_id]
    ):

        await update.message.reply_text(
            f"❌ لا يوجد تنبيه لـ {symbol}."
        )

        return

    del alerts[
        chat_id
    ][symbol]

    save_alerts(alerts)

    await update.message.reply_text(
        f"🗑️ تم حذف تنبيه {symbol}."
    )


# ============================================================
# فحص التنبيهات
# ============================================================

async def check_alerts(
    context: ContextTypes.DEFAULT_TYPE
):

    alerts = load_alerts()

    if not alerts:
        return

    for chat_id, user_alerts in list(
        alerts.items()
    ):

        for symbol, info in list(
            user_alerts.items()
        ):

            try:

                data = yf.Ticker(
                    symbol
                ).history(
                    period="1d",
                    interval="1m"
                )

                if data.empty:
                    continue

                price = float(
                    data["Close"].iloc[-1]
                )

                target = float(
                    info["target"]
                )

                if price >= target:

                    await context.bot.send_message(
                        chat_id=int(chat_id),
                        text=f"""
🚨 تنبيه سهم

📊 {symbol}

💰 السعر:
${price:.2f}

🎯 السعر المستهدف:
${target:.2f}

✅ وصل السهم إلى السعر المحدد.
"""
                    )

                    del alerts[
                        chat_id
                    ][symbol]

                    save_alerts(alerts)

            except Exception as error:

                print(
                    f"ALERT ERROR {symbol}:",
                    error
                )


# ============================================================
# الأزرار
# ============================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = update.message.text

    if text == "📊 تحليل سهم":

        await update.message.reply_text(
            "📊 أرسل رمز السهم.\n\n"
            "مثال:\n"
            "AAPL"
        )

    elif text == "📑 الخيارات":

        await update.message.reply_text(
            "📑 اكتب:\n\n"
            "/o AAPL\n\n"
            "مثال:\n"
            "/o NVDA"
        )

    elif text == "💰 الأرباح":

        await update.message.reply_text(
            "💰 اكتب:\n\n"
            "/e AAPL\n\n"
            "أو:\n"
            "e AAPL"
        )

    elif text == "📰 أخبار الشركة":

        await update.message.reply_text(
            "📰 اكتب:\n\n"
            "/news AAPL\n\n"
            "مثال آخر:\n"
            "n TSLA"
        )

    elif text == "🔔 تنبيه":

        await update.message.reply_text(
            "🔔 اكتب:\n\n"
            "/alert AAPL 300\n\n"
            "مثال: تنبيه AAPL عند $300"
        )

    elif text == "📋 تنبيهاتي":

        await alerts_command(
            update,
            context
        )

    elif text == "❓ المساعدة":

        await help_command(
            update,
            context
        )


# ============================================================
# استقبال الرسائل
# ============================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = update.message.text.strip()

    # e AAPL
    if text.lower().startswith("e "):

        await earnings_shortcut(
            update,
            context
        )

        return

    # n AAPL
    if text.lower().startswith("n "):

        parts = text.split()

        if len(parts) != 2:

            await update.message.reply_text(
                "اكتب:\nn AAPL"
            )

            return

        symbol = parts[1].upper()

        message = await update.message.reply_text(
            f"📰 جاري جلب أخبار {symbol}..."
        )

        result = get_news(symbol)

        await message.edit_text(
            result,
            disable_web_page_preview=True
        )

        return

    # o AAPL
    if text.lower().startswith("o "):

        parts = text.split()

        if len(parts) != 2:

            await update.message.reply_text(
                "اكتب:\no AAPL"
            )

            return

        symbol = parts[1].upper()

        message = await update.message.reply_text(
            f"📑 جاري تحليل خيارات {symbol}..."
        )

        try:

            data = yf.Ticker(symbol).history(
                period="6mo",
                interval="1d"
            )

            if data.empty:

                await message.edit_text(
                    f"❌ لا توجد بيانات لـ {symbol}."
                )

                return

            price = float(
                data["Close"].iloc[-1]
            )

            supports, resistances = (
                get_support_resistance(
                    data,
                    price
                )
            )

            result = get_options(
                symbol,
                price,
                supports,
                resistances
            )

            await message.edit_text(result)

        except Exception as error:

            print(
                "OPTIONS MESSAGE ERROR:",
                error
            )

            await message.edit_text(
                "❌ تعذر جلب بيانات الخيارات."
            )

        return

    # تجاهل الرسائل الطويلة
    if len(text) > 10:
        return

    symbol = text.upper()

    message = await update.message.reply_text(
        f"🔍 جاري تحليل {symbol}..."
    )

    result = analyze_stock(symbol)

    if result is None:

        await message.edit_text(
            f"❌ لم أجد بيانات لـ {symbol}."
        )

        return

    await message.edit_text(result)


# ============================================================
# تشغيل البوت
# ============================================================

def main():

    print("")
    print("================================")
    print("🚀 STOCK TALAL BOT")
    print("================================")
    print("📊 التحليل جاهز")
    print("🛡️ الدعم والمقاومة جاهزة")
    print("📑 الخيارات جاهزة")
    print("💰 الأرباح جاهزة")
    print("📰 الأخبار جاهزة")
    print("🔔 التنبيهات جاهزة")
    print("================================")
    print("")

    if not TOKEN:

        print(
            "❌ TOKEN غير موجود في Environment Variables"
        )

        return

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    # ========================================================
    # الأوامر
    # ========================================================

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    app.add_handler(
        CommandHandler(
            "analyze",
            analyze_command
        )
    )

    app.add_handler(
        CommandHandler(
            "o",
            options_command
        )
    )

    app.add_handler(
        CommandHandler(
            "e",
            earnings_short_command
        )
    )

    app.add_handler(
        CommandHandler(
            "earnings",
            earnings_command
        )
    )

    app.add_handler(
        CommandHandler(
            "news",
            news_command
        )
    )

    app.add_handler(
        CommandHandler(
            "alert",
            alert_command
        )
    )

    app.add_handler(
        CommandHandler(
            "alerts",
            alerts_command
        )
    )

    app.add_handler(
        CommandHandler(
            "remove",
            remove_command
        )
    )

    # ========================================================
    # الأزرار
    # ========================================================

    app.add_handler(
        MessageHandler(
            filters.Regex(
                r"^(📊 تحليل سهم|📑 الخيارات|💰 الأرباح|📰 أخبار الشركة|🔔 تنبيه|📋 تنبيهاتي|❓ المساعدة)$"
            ),
            button_handler
        )
    )

    # ========================================================
    # الرسائل
    # ========================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    # ========================================================
    # فحص التنبيهات
    # ========================================================

    if app.job_queue is not None:

        app.job_queue.run_repeating(
            check_alerts,
            interval=60,
            first=10
        )

    else:

        print(
            "⚠️ JobQueue غير مفعلة."
        )

    print(
        "🤖 البوت يعمل الآن..."
    )

    app.run_polling()


# ============================================================
# البداية
# ============================================================

if __name__ == "__main__":
    main()
