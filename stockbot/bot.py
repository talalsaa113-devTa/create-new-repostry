import logging
import pandas as pd
import numpy as np
import yfinance as yf

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ============================================================
# إعداد التسجيل
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# ============================================================
# إعدادات البوت
# ============================================================

TOKEN = "YOUR_NEW_BOT_TOKEN"

# ============================================================
# القائمة الرئيسية
# ============================================================

def main_keyboard():

    keyboard = [
        [
            InlineKeyboardButton("💰 الأرباح", callback_data="earnings"),
            InlineKeyboardButton("📊 تحليل السهم", callback_data="analysis"),
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# RSI
# ============================================================

def calculate_rsi(close, window=14):

    delta = close.diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


# ============================================================
# MACD
# ============================================================

def calculate_macd(close):

    fast = close.ewm(span=12, adjust=False).mean()
    slow = close.ewm(span=26, adjust=False).mean()

    macd = fast - slow
    signal = macd.ewm(span=9, adjust=False).mean()

    return macd, signal


# ============================================================
# الدعم والمقاومة
# ============================================================

def get_support_resistance(data, current_price):

    highs = data["High"].tail(30)
    lows = data["Low"].tail(30)

    supports = sorted(
        [float(x) for x in lows if x < current_price],
        reverse=True
    )[:3]

    resistances = sorted(
        [float(x) for x in highs if x > current_price]
    )[:3]

    return supports, resistances


# ============================================================
# تحليل السهم
# ============================================================

def analyze_stock(symbol):

    symbol = symbol.upper().strip()

    try:

        ticker = yf.Ticker(symbol)

        data = ticker.history(
            period="6mo",
            interval="1d",
            auto_adjust=False
        )

        if data.empty or len(data) < 50:
            return (
                f"❌ لم أتمكن من الحصول على بيانات كافية للسهم "
                f"`{symbol}`.\n\n"
                f"تأكد أن رمز السهم صحيح."
            )

        close = data["Close"].dropna()

        # السعر
        price = float(close.iloc[-1])

        # اليوم السابق
        previous = float(close.iloc[-2])

        change = ((price - previous) / previous) * 100

        # المتوسطات
        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1])

        # RSI
        rsi = calculate_rsi(close)
        rsi_value = float(rsi.iloc[-1])

        if rsi_value >= 70:
            rsi_status = "🔴 تشبع شراء"
        elif rsi_value <= 30:
            rsi_status = "🟢 تشبع بيع"
        else:
            rsi_status = "⚪ طبيعي"

        # MACD
        macd, signal = calculate_macd(close)

        macd_value = float(macd.iloc[-1])
        signal_value = float(signal.iloc[-1])

        if macd_value > signal_value:
            macd_status = "🟢 إيجابي"
        else:
            macd_status = "🔴 سلبي"

        # أعلى وأدنى 30 يوم
        high30 = float(data["High"].tail(30).max())
        low30 = float(data["Low"].tail(30).min())

        # الاتجاه
        if price > ma20 > ma50:
            trend = "🟢 صاعد"

        elif price < ma20 < ma50:
            trend = "🔴 هابط"

        else:
            trend = "🟡 متذبذب"

        # الدعم والمقاومة
        supports, resistances = get_support_resistance(
            data,
            price
        )

        # ====================================================
        # Score
        # ====================================================

        score = 0

        if price > ma20:
            score += 1

        if ma20 > ma50:
            score += 1

        if macd_value > signal_value:
            score += 1

        if 30 <= rsi_value <= 70:
            score += 1

        if price >= high30 * 0.97:
            score += 1

        # الإشارة النهائية
        if score >= 4:
            final_signal = "🟢 إيجابية"

        elif score <= 1:
            final_signal = "🔴 سلبية"

        else:
            final_signal = "🟡 محايدة"

        # التغير اليومي
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

            for i, level in enumerate(supports, start=1):

                distance = ((level - price) / price) * 100

                support_text += (
                    f"{i}️⃣ ${level:.2f} "
                    f"({distance:.2f}%)\n"
                )

        else:

            support_text = "❌ لا يوجد دعم واضح.\n"

        # ====================================================
        # المقاومة
        # ====================================================

        if resistances:

            resistance_text = ""

            for i, level in enumerate(resistances, start=1):

                distance = ((level - price) / price) * 100

                resistance_text += (
                    f"{i}️⃣ ${level:.2f} "
                    f"(+{distance:.2f}%)\n"
                )

        else:

            resistance_text = "❌ لا توجد مقاومة واضحة.\n"

        # ====================================================
        # النتيجة
        # ====================================================

        result = f"""
📊 **تحليل السهم: {symbol}**

━━━━━━━━━━━━━━━━━━

💰 **السعر الحالي:** ${price:.2f}

📅 **التغير اليومي:** {daily_change}

📈 **الاتجاه:** {trend}

━━━━━━━━━━━━━━━━━━

📊 **RSI:** {rsi_value:.1f}
الحالة: {rsi_status}

📉 **MACD:** {macd_status}

━━━━━━━━━━━━━━━━━━

📏 **MA20:** ${ma20:.2f}

📏 **MA50:** ${ma50:.2f}

━━━━━━━━━━━━━━━━━━

🎯 **أعلى 30 يوم:** ${high30:.2f}

🎯 **أدنى 30 يوم:** ${low30:.2f}

━━━━━━━━━━━━━━━━━━

🛡️ **الدعوم:**

{support_text}

🚧 **المقاومات:**

{resistance_text}

━━━━━━━━━━━━━━━━━━

🔔 **الإشارة:** {final_signal}

⭐ **القوة:** {score}/5

━━━━━━━━━━━━━━━━━━

⚠️ تحليل آلي وليس توصية مالية.
"""

        return result

    except Exception as e:

        logger.error(
            f"Error analyzing {symbol}: {e}"
        )

        return (
            f"❌ حدث خطأ أثناء تحليل السهم `{symbol}`.\n\n"
            f"تأكد من صحة رمز السهم."
        )


# ============================================================
# جلب موعد الأرباح القادم
# ============================================================

def get_next_earnings(ticker):

    try:

        calendar = ticker.calendar

        if calendar is None:
            return "غير متوفر"

        # إذا كان DataFrame
        if isinstance(calendar, pd.DataFrame):

            if "Earnings Date" in calendar.index:

                value = calendar.loc["Earnings Date"]

                if isinstance(value, pd.Series):

                    if len(value) > 0:

                        return str(
                            value.iloc[0]
                        ).split()[0]

                return str(value).split()[0]

        # إذا كان Dictionary
        if isinstance(calendar, dict):

            earnings_date = calendar.get(
                "Earnings Date"
            )

            if earnings_date is not None:

                if isinstance(
                    earnings_date,
                    (list, tuple)
                ):

                    if len(earnings_date) > 0:

                        return str(
                            earnings_date[0]
                        ).split()[0]

                return str(
                    earnings_date
                ).split()[0]

        return "غير متوفر"

    except Exception as e:

        logger.error(
            f"Earnings calendar error: {e}"
        )

        return "غير متوفر"


# ============================================================
# تقرير الأرباح
# ============================================================

def get_earnings_full(symbol):

    symbol = symbol.upper().strip()

    try:

        ticker = yf.Ticker(symbol)

        # التحقق من وجود السهم
        info = ticker.fast_info

        # موعد الأرباح
        next_earnings = get_next_earnings(
            ticker
        )

        # ====================================================
        # الأرباح الفصلية
        # ====================================================

        earnings_text = ""

        try:

            quarterly = ticker.quarterly_income_stmt

            if (
                quarterly is not None
                and not quarterly.empty
            ):

                # البحث عن Revenue
                revenue_row = None

                possible_rows = [
                    "Total Revenue",
                    "Operating Revenue",
                    "Revenue"
                ]

                for row_name in possible_rows:

                    if row_name in quarterly.index:

                        revenue_row = row_name
                        break

                earnings_text = (
                    "📈 **الإيرادات - آخر 4 أرباع:**\n\n"
                )

                if revenue_row:

                    values = quarterly.loc[
                        revenue_row
                    ].dropna()

                    values = values.iloc[:4]

                    for date, value in values.items():

                        try:

                            revenue = float(value)

                            earnings_text += (
                                f"• {str(date)[:10]} : "
                                f"${revenue:,.0f}\n"
                            )

                        except:

                            earnings_text += (
                                f"• {str(date)[:10]} : "
                                f"غير متوفر\n"
                            )

                else:

                    earnings_text += (
                        "❌ بيانات الإيرادات غير متوفرة."
                    )

            else:

                earnings_text = (
                    "📈 بيانات الأرباح غير متوفرة حالياً."
                )

        except Exception as e:

            logger.error(
                f"Quarterly earnings error: {e}"
            )

            earnings_text = (
                "📈 بيانات الأرباح غير متوفرة حالياً."
            )

        # ====================================================
        # EPS
        # ====================================================

        eps_text = ""

        try:

            earnings_dates = ticker.get_earnings_dates(
                limit=8
            )

            if (
                earnings_dates is not None
                and not earnings_dates.empty
            ):

                eps_text = (
                    "\n📊 **آخر نتائج EPS المتاحة:**\n\n"
                )

                count = 0

                for date, row in earnings_dates.iterrows():

                    eps_actual = row.get(
                        "Reported EPS",
                        np.nan
                    )

                    eps_estimate = row.get(
                        "EPS Estimate",
                        np.nan
                    )

                    if pd.notna(eps_actual):

                        eps_text += (
                            f"• {str(date)[:10]} | "
                            f"EPS: {eps_actual}"
                        )

                        if pd.notna(eps_estimate):

                            eps_text += (
                                f" | المتوقع: "
                                f"{eps_estimate}"
                            )

                        eps_text += "\n"

                        count += 1

                    if count >= 4:
                        break

        except Exception as e:

            logger.error(
                f"EPS error: {e}"
            )

        # ====================================================
        # النتيجة
        # ====================================================

        result = f"""
💰 **تقرير أرباح: {symbol}**

━━━━━━━━━━━━━━━━━━

📅 **موعد الأرباح القادم:**

`{next_earnings}`

━━━━━━━━━━━━━━━━━━

{earnings_text}

{eps_text}

━━━━━━━━━━━━━━━━━━

⚠️ البيانات يتم جلبها آلياً وقد تتأخر أو تتغير حسب مصدر البيانات.
"""

        return result

    except Exception as e:

        logger.error(
            f"Error fetching earnings for {symbol}: {e}"
        )

        return (
            f"❌ لم أتمكن من جلب بيانات الأرباح "
            f"للسهم `{symbol}`.\n\n"
            f"تأكد أن رمز السهم صحيح."
        )


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    context.user_data["mode"] = None

    await update.message.reply_text(
        "👋 **أهلاً بك في بوت تحليل الأسهم**\n\n"
        "اختر الخدمة التي تريدها:",
        reply_markup=main_keyboard()
    )


# ============================================================
# الأزرار
# ============================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    if query.data == "earnings":

        context.user_data["mode"] = "earnings"

        await query.edit_message_text(
            "💰 **الأرباح**\n\n"
            "أرسل رمز السهم فقط.\n\n"
            "مثال:\n"
            "`AAPL`"
        )

    elif query.data == "analysis":

        context.user_data["mode"] = "analysis"

        await query.edit_message_text(
            "📊 **تحليل السهم**\n\n"
            "أرسل رمز السهم فقط.\n\n"
            "مثال:\n"
            "`AAPL`"
        )


# ============================================================
# استقبال رمز السهم
# ============================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = update.message.text.strip().upper()

    mode = context.user_data.get(
        "mode"
    )

    # السماح برمز السهم فقط
    if not text.isalpha() or len(text) > 6:

        await update.message.reply_text(
            "⚠️ أرسل رمز السهم فقط.\n\n"
            "مثال:\n"
            "`AAPL`"
        )

        return

    # ========================================================
    # الأرباح
    # ========================================================

    if mode == "earnings":

        wait_msg = await update.message.reply_text(
            f"⏳ جاري جلب بيانات أرباح `{text}`..."
        )

        result = get_earnings_full(text)

        await wait_msg.edit_text(
            result,
            reply_markup=main_keyboard()
        )

        context.user_data["mode"] = None

    # ========================================================
    # التحليل
    # ========================================================

    elif mode == "analysis":

        wait_msg = await update.message.reply_text(
            f"🔍 جاري تحليل السهم `{text}`..."
        )

        result = analyze_stock(text)

        await wait_msg.edit_text(
            result,
            reply_markup=main_keyboard()
        )

        context.user_data["mode"] = None

    # ========================================================
    # إذا لم يختر خدمة
    # ========================================================

    else:

        await update.message.reply_text(
            "اختر الخدمة أولاً:",
            reply_markup=main_keyboard()
        )


# ============================================================
# تشغيل البوت
# ============================================================

def main():

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    # /start
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # أزرار القائمة
    app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    # الرسائل
    app.add_handler(
        MessageHandler(
            filters.TEXT & (~filters.COMMAND),
            handle_message
        )
    )

    print(
        "🤖 البوت يعمل..."
    )

    app.run_polling()


# ============================================================
# البداية
# ============================================================

if __name__ == "__main__":
    main()
