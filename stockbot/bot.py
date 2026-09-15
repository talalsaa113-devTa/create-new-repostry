import logging
import pandas as pd
import numpy as np
import yfinance as yf

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
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
# التوكن
# ============================================================

# مهم: ضع التوكن الجديد هنا
TOKEN = "YOUR_NEW_BOT_TOKEN"


# ============================================================
# القائمة الرئيسية
# ============================================================

def main_menu():

    keyboard = [
        [
            InlineKeyboardButton(
                "💰 الأرباح",
                callback_data="earnings"
            ),
            InlineKeyboardButton(
                "📊 تحليل السهم",
                callback_data="analysis"
            )
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

    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()

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
# الدعم والمقاومة
# ============================================================

def get_support_resistance(data, price):

    highs = data["High"].tail(30)
    lows = data["Low"].tail(30)

    supports = sorted(
        [float(x) for x in lows if x < price],
        reverse=True
    )[:3]

    resistances = sorted(
        [float(x) for x in highs if x > price]
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
                f"❌ لم أجد بيانات كافية للسهم "
                f"`{symbol}`."
            )

        close = data["Close"].dropna()

        # السعر الحالي
        price = float(close.iloc[-1])

        # السعر السابق
        previous = float(close.iloc[-2])

        change = (
            (price - previous)
            / previous
        ) * 100

        # المتوسطات
        ma20 = float(
            close.rolling(20).mean().iloc[-1]
        )

        ma50 = float(
            close.rolling(50).mean().iloc[-1]
        )

        # RSI
        rsi = calculate_rsi(close)

        rsi_value = float(
            rsi.iloc[-1]
        )

        if rsi_value >= 70:

            rsi_status = "🔴 تشبع شراء"

        elif rsi_value <= 30:

            rsi_status = "🟢 تشبع بيع"

        else:

            rsi_status = "⚪ طبيعي"

        # MACD
        macd, signal = calculate_macd(close)

        macd_value = float(
            macd.iloc[-1]
        )

        signal_value = float(
            signal.iloc[-1]
        )

        if macd_value > signal_value:

            macd_status = "🟢 إيجابي"

        else:

            macd_status = "🔴 سلبي"

        # أعلى وأدنى 30 يوم
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

        # الدعم والمقاومة
        supports, resistances = (
            get_support_resistance(
                data,
                price
            )
        )

        # ====================================================
        # القوة
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

        # ====================================================
        # الدعوم
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

        else:

            support_text = (
                "❌ لا يوجد دعم واضح.\n"
            )

        # ====================================================
        # المقاومات
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

        else:

            resistance_text = (
                "❌ لا توجد مقاومة واضحة.\n"
            )

        # ====================================================
        # التقرير
        # ====================================================

        return f"""
📊 **تحليل السهم: {symbol}**

━━━━━━━━━━━━━━━━━━

💰 السعر الحالي:
`${price:.2f}`

📅 التغير اليومي:
`{daily_change}`

📈 الاتجاه:
`{trend}`

━━━━━━━━━━━━━━━━━━

📊 RSI:
`{rsi_value:.1f}`

الحالة:
`{rsi_status}`

📉 MACD:
`{macd_status}`

━━━━━━━━━━━━━━━━━━

📏 MA20:
`${ma20:.2f}`

📏 MA50:
`${ma50:.2f}`

━━━━━━━━━━━━━━━━━━

🎯 أعلى 30 يوم:
`${high30:.2f}`

🎯 أدنى 30 يوم:
`${low30:.2f}`

━━━━━━━━━━━━━━━━━━

🛡️ **الدعوم:**

{support_text}

🚧 **المقاومات:**

{resistance_text}

━━━━━━━━━━━━━━━━━━

🔔 الإشارة:
`{final_signal}`

⭐ القوة:
`{score}/5`

━━━━━━━━━━━━━━━━━━

⚠️ تحليل آلي وليس توصية مالية.
"""


# ============================================================
# موعد الأرباح
# ============================================================

def get_next_earnings(ticker):

    try:

        calendar = ticker.calendar

        if calendar is None:
            return "غير متوفر"

        if isinstance(calendar, pd.DataFrame):

            if "Earnings Date" in calendar.index:

                dates = calendar.loc[
                    "Earnings Date"
                ]

                if isinstance(
                    dates,
                    pd.Series
                ):

                    if len(dates) > 0:

                        return str(
                            dates.iloc[0]
                        ).split()[0]

                return str(
                    dates
                ).split()[0]

        return "غير متوفر"

    except Exception as e:

        logger.error(
            f"Earnings date error: {e}"
        )

        return "غير متوفر"


# ============================================================
# الأرباح
# ============================================================

def get_earnings(symbol):

    symbol = symbol.upper().strip()

    try:

        ticker = yf.Ticker(symbol)

        # موعد الأرباح
        next_date = get_next_earnings(
            ticker
        )

        # ====================================================
        # القوائم المالية
        # ====================================================

        income = ticker.quarterly_income_stmt

        revenue_text = ""

        if (
            income is not None
            and not income.empty
        ):

            revenue_row = None

            for row in [
                "Total Revenue",
                "Operating Revenue",
                "Revenue"
            ]:

                if row in income.index:

                    revenue_row = row
                    break

            if revenue_row:

                revenue_text = (
                    "📈 **الإيرادات - آخر 4 أرباع:**\n\n"
                )

                values = income.loc[
                    revenue_row
                ].dropna().iloc[:4]

                for date, value in values.items():

                    revenue_text += (
                        f"• {str(date)[:10]} | "
                        f"${float(value):,.0f}\n"
                    )

            else:

                revenue_text = (
                    "📈 الإيرادات غير متوفرة."
                )

        else:

            revenue_text = (
                "📈 بيانات الأرباح غير متوفرة."
            )

        # ====================================================
        # EPS
        # ====================================================

        eps_text = ""

        try:

            earnings_dates = (
                ticker.get_earnings_dates(
                    limit=8
                )
            )

            if (
                earnings_dates is not None
                and not earnings_dates.empty
            ):

                eps_text = (
                    "\n📊 **EPS - آخر النتائج:**\n\n"
                )

                count = 0

                for date, row in earnings_dates.iterrows():

                    actual = row.get(
                        "Reported EPS",
                        np.nan
                    )

                    estimate = row.get(
                        "EPS Estimate",
                        np.nan
                    )

                    if pd.notna(actual):

                        eps_text += (
                            f"• {str(date)[:10]} | "
                            f"Actual: {actual}"
                        )

                        if pd.notna(estimate):

                            eps_text += (
                                f" | Estimate: "
                                f"{estimate}"
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
        # التقرير النهائي
        # ====================================================

        return f"""
💰 **تقرير أرباح: {symbol}**

━━━━━━━━━━━━━━━━━━

📅 موعد الأرباح القادم:

`{next_date}`

━━━━━━━━━━━━━━━━━━

{revenue_text}

{eps_text}

━━━━━━━━━━━━━━━━━━

⚠️ البيانات يتم جلبها آلياً.
"""

    except Exception as e:

        logger.error(
            f"Earnings error {symbol}: {e}"
        )

        return (
            f"❌ لم أتمكن من جلب أرباح "
            f"`{symbol}`.\n\n"
            f"تأكد من رمز السهم."
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
        "👋 **أهلاً بك**\n\n"
        "اختر الخدمة التي تريدها:",
        reply_markup=main_menu()
    )


# ============================================================
# الضغط على الأزرار
# ============================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    # ========================================================
    # الأرباح
    # ========================================================

    if query.data == "earnings":

        context.user_data["mode"] = "earnings"

        await query.message.reply_text(
            "💰 **الأرباح**\n\n"
            "📩 أرسل رمز السهم بهذه الصيغة:\n\n"
            "`E NVDA`\n\n"
            "مثال آخر:\n"
            "`E AAPL`"
        )

    # ========================================================
    # تحليل السهم
    # ========================================================

    elif query.data == "analysis":

        context.user_data["mode"] = "analysis"

        await query.message.reply_text(
            "📊 **تحليل السهم**\n\n"
            "📩 أرسل رمز السهم فقط:\n\n"
            "`NVDA`\n\n"
            "مثال آخر:\n"
            "`AAPL`"
        )


# ============================================================
# استقبال الرسائل
# ============================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = update.message.text.strip().upper()

    mode = context.user_data.get(
        "mode"
    )

    # ========================================================
    # وضع الأرباح
    # ========================================================

    if mode == "earnings":

        # يجب أن تكون الصيغة E NVDA
        parts = text.split()

        if (
            len(parts) != 2
            or parts[0] != "E"
            or not parts[1].isalpha()
        ):

            await update.message.reply_text(
                "⚠️ الصيغة غير صحيحة.\n\n"
                "أرسلها بهذا الشكل:\n"
                "`E NVDA`"
            )

            return

        symbol = parts[1]

        wait_msg = await update.message.reply_text(
            f"⏳ جاري جلب أرباح `{symbol}`..."
        )

        result = get_earnings(symbol)

        await wait_msg.edit_text(
            result,
            reply_markup=main_menu()
        )

        context.user_data["mode"] = None

    # ========================================================
    # وضع تحليل السهم
    # ========================================================

    elif mode == "analysis":

        # يجب أن يكون رمز السهم فقط
        if (
            not text.isalpha()
            or len(text) > 6
        ):

            await update.message.reply_text(
                "⚠️ أرسل رمز السهم فقط.\n\n"
                "مثال:\n"
                "`NVDA`"
            )

            return

        symbol = text

        wait_msg = await update.message.reply_text(
            f"⏳ جاري تحليل `{symbol}`..."
        )

        result = analyze_stock(symbol)

        await wait_msg.edit_text(
            result,
            reply_markup=main_menu()
        )

        context.user_data["mode"] = None

    # ========================================================
    # لا يوجد اختيار
    # ========================================================

    else:

        await update.message.reply_text(
            "اختر الخدمة أولاً:",
            reply_markup=main_menu()
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

    # Start
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # الأزرار
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
        "🤖 البوت يعمل بنجاح..."
    )

    app.run_polling()


if __name__ == "__main__":
    main()
