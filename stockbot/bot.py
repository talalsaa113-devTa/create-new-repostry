import json
import os

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
#did h
# ============================================================

import os

TOKEN = os.getenv("TOKEN")


ALERTS_FILE = "alerts.json"


# ============================================================
# التنبيهات
# ============================================================

def load_alerts():

    if not os.path.exists(ALERTS_FILE):
        return {}

    try:

        with open(
            ALERTS_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except:

        return {}


def save_alerts(alerts):

    with open(
        ALERTS_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            alerts,
            file,
            ensure_ascii=False,
            indent=2
        )


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

    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    macd = ema12 - ema26

    signal = macd.ewm(
        span=9,
        adjust=False
    ).mean()

    return macd, signal


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

        # الاتجاه

        if price > ma20 > ma50:

            trend = "🟢 صاعد"

        elif price < ma20 < ma50:

            trend = "🔴 هابط"

        else:

            trend = "🟡 متذبذب"

        # RSI

        if rsi_value < 30:

            rsi_status = "🟢 تشبع بيع"

        elif rsi_value > 70:

            rsi_status = "🔴 تشبع شراء"

        else:

            rsi_status = "⚪ طبيعي"

        # MACD

        if macd_value > signal_value:

            macd_status = "🟢 إيجابي"

        else:

            macd_status = "🔴 سلبي"

        # نقاط التحليل

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

        # الإشارة

        if score >= 4:

            final_signal = "🟢 إيجابية"

        elif score <= 1:

            final_signal = "🔴 سلبية"

        else:

            final_signal = "🟡 محايدة"

        # التغير

        if change > 0:

            daily_change = f"🟢 +{change:.2f}%"

        elif change < 0:

            daily_change = f"🔴 {change:.2f}%"

        else:

            daily_change = "⚪ 0.00%"

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

🎯 أعلى 30 يوم:
${high30:.2f}

🎯 أدنى 30 يوم:
${low30:.2f}

━━━━━━━━━━━━━━━━━━

🔔 الإشارة:
{final_signal}

⭐ القوة:
{score}/5

━━━━━━━━━━━━━━━━━━

⚠️ تحليل آلي وليس توصية مالية.
"""

    except Exception as error:

        print("ANALYSIS ERROR:", error)

        return None


# ============================================================
# الأرباح
# ============================================================

def get_earnings(symbol):

    symbol = symbol.upper().strip()

    try:

        stock = yf.Ticker(symbol)

        # ----------------------------------------------------
        # موعد الأرباح القادم
        # ----------------------------------------------------

        calendar = stock.calendar

        earnings_date = None

        try:

            if isinstance(calendar, dict):

                dates = calendar.get(
                    "Earnings Date"
                )

                if dates:

                    earnings_date = dates[0]

            else:

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

                    earnings_date = (
                        earnings_dates
                    )

        except:

            pass

        # ----------------------------------------------------
        # الأرباح السابقة
        # ----------------------------------------------------

        earnings = stock.get_earnings_dates(
            limit=8
        )

        text = f"""
💰 أرباح {symbol}

━━━━━━━━━━━━━━━━━━

📅 إعلان الأرباح القادم:
"""

        if earnings_date:

            text += (
                f"{str(earnings_date)[:10]}\n"
            )

        else:

            text += "غير متوفر حاليًا\n"

        text += """
━━━━━━━━━━━━━━━━━━

📋 آخر 4 إعلانات:

"""

        if earnings is None or earnings.empty:

            text += "❌ لا توجد بيانات أرباح متاحة.\n"

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

                actual_text = (
                    f"${float(actual):.2f}"
                    if actual is not None
                    else "غير متوفر"
                )

                estimate_text = (
                    f"${float(estimate):.2f}"
                    if estimate is not None
                    else "غير متوفر"
                )

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

                except:

                    result = "⚪ غير متوفر"

                text += (
                    f"📅 {str(index)[:10]}\n"
                    f"💵 الفعلي: {actual_text}\n"
                    f"🎯 المتوقع: {estimate_text}\n"
                    f"{result}\n\n"
                )

        text += """
━━━━━━━━━━━━━━━━━━

⚠️ قد تختلف البيانات حسب توفر
المصدر وتوقيت تحديثه.
"""

        return text

    except Exception as error:

        print("EARNINGS ERROR:", error)

        return f"""
❌ تعذر جلب أرباح {symbol}.

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
        ["📊 تحليل سهم", "💰 الأرباح"],
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

💰 الأرباح:
e AAPL

🔔 تنبيه:
استخدم:
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
# اختصار الأرباح
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
# أمر الأرباح الكامل
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

    except:

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

    del alerts[chat_id][symbol]

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
# التعامل مع الأزرار
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

    elif text == "💰 الأرباح":

        await update.message.reply_text(
            "💰 أرسل:\n\n"
            "e AAPL\n\n"
            "مثال آخر:\n"
            "e TSLA"
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

    # زر الأرباح المختصر
    if text.lower().startswith("e "):

        await earnings_shortcut(
            update,
            context
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
    print("💰 الأرباح جاهزة")
    print("🔔 التنبيهات جاهزة")
    print("================================")
    print("")

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    # --------------------------------
    # الأوامر
    # --------------------------------

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
            "earnings",
            earnings_command
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

    # --------------------------------
    # الأزرار
    # --------------------------------

    app.add_handler(
        MessageHandler(
            filters.Regex(
                r"^(📊 تحليل سهم|💰 الأرباح|🔔 تنبيه|📋 تنبيهاتي|❓ المساعدة)$"
            ),
            button_handler
        )
    )

    # --------------------------------
    # الرسائل والأسهم
    # --------------------------------

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    # --------------------------------
    # فحص التنبيهات
    # --------------------------------

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
            'ثبتها بالأمر: '
            'pip install -U "python-telegram-bot[job-queue]"'
        )

    # --------------------------------
    # تشغيل
    # --------------------------------

    print("🤖 البوت يعمل الآن...")

    app.run_polling()


# ============================================================
# البداية
# ============================================================

if __name__ == "__main__":
    main()
