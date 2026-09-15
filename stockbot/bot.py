import logging
import pandas as pd
import numpy as np
import yfinance as yf
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# إعداد التسجيل لمتابعة الأخطاء
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================
# الإعدادات الخاصة بك
# ============================================================
TOKEN = "8634652596:AAGs4bPIGYV-aHMcTh6Xv_cU2WKLofKL1Io"
MY_CHAT_ID = "1718922948"

# ============================================================
# الدوال المساعدة للتحليل الفني
# ============================================================

def calculate_rsi(close, window=14):
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(close, slow=26, fast=12, signal=9):
    exp1 = close.ewm(span=fast, adjust=False).mean()
    exp2 = close.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

def get_support_resistance(data, current_price):
    highs = data['High'].tail(30)
    lows = data['Low'].tail(30)
    
    supports = sorted([float(x) for x in lows if x < current_price], reverse=True)[:3]
    resistances = sorted([float(x) for x in highs if x > current_price])[:3]
    
    return supports, resistances

def get_options(symbol, price, supports, resistances):
    return "📊 خيارات العقود: غير متوفرة حالياً أو تتطلب تفعيل بيانات متقدمة."

# ============================================================
# دالة تحليل السهم - شاملة
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

        # RSI
        rsi = calculate_rsi(close)
        rsi_value = float(rsi.iloc[-1])

        if rsi_value < 30:
            rsi_status = "🟢 تشبع بيع"
        elif rsi_value > 70:
            rsi_status = "🔴 تشبع شراء"
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
        supports, resistances = get_support_resistance(
            data,
            price
        )

        # الإشارة
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

        # التغير اليومي
        if change > 0:
            daily_change = f"🟢 +{change:.2f}%"
        elif change < 0:
            daily_change = f"🔴 {change:.2f}%"
        else:
            daily_change = "⚪ 0.00%"

        # الدعوم
        if supports:
            support_text = ""
            for i, level in enumerate(supports, start=1):
                distance = ((level - price) / price) * 100
                support_text += f"{i}️⃣ ${level:.2f} ({distance:.2f}%)\n"
            nearest_support = supports[0]
        else:
            support_text = "❌ لا يوجد مستوى دعم واضح.\n"
            nearest_support = None

        # المقاومات
        if resistances:
            resistance_text = ""
            for i, level in enumerate(resistances, start=1):
                distance = ((level - price) / price) * 100
                resistance_text += f"{i}️⃣ ${level:.2f} (+{distance:.2f}%)\n"
            nearest_resistance = resistances[0]
        else:
            resistance_text = "❌ لا يوجد مستوى مقاومة واضح.\n"
            nearest_resistance = None

        # السيناريو القادم
        scenario = ""
        if nearest_resistance is not None and nearest_support is not None:
            resistance_distance = ((nearest_resistance - price) / price) * 100
            support_distance = ((nearest_support - price) / price) * 100

            if trend == "🟢 صاعد":
                if len(resistances) > 1:
                    next_target = resistances[1]
                    scenario = f"\n🟢 السيناريو الأقرب:\nاختراق المقاومة: ${nearest_resistance:.2f}\n🎯 الهدف التالي: ${next_target:.2f}\n"
                else:
                    scenario = f"\n🟢 السيناريو الأقرب:\nاختراق المقاومة: ${nearest_resistance:.2f}\n🎯 قد يستهدف السهم مستويات أعلى.\n"
            elif trend == "🔴 هابط":
                if len(supports) > 1:
                    next_target = supports[1]
                    scenario = f"\n🔴 السيناريو الأقرب:\nكسر الدعم: ${nearest_support:.2f}\n🎯 الهدف التالي: ${next_target:.2f}\n"
                else:
                    scenario = f"\n🔴 السيناريو الأقرب:\nكسر الدعم: ${nearest_support:.2f}\n🎯 قد يبحث السهم عن دعم أدنى.\n"
            else:
                if resistance_distance < abs(support_distance):
                    scenario = f"\n🟡 السيناريو الأقرب:\n🚧 المقاومة: ${nearest_resistance:.2f}\n🛡️ الدعم: ${nearest_support:.2f}\nراقب الاختراق أو الكسر قبل اتخاذ القرار.\n"
                else:
                    scenario = f"\n🟡 السيناريو الأقرب:\n🛡️ الدعم: ${nearest_support:.2f}\n🚧 المقاومة: ${nearest_resistance:.2f}\nراقب الارتداد أو الكسر قبل اتخاذ القرار.\n"
        else:
            scenario = "\n🟡 لا يوجد مستوى واضح كافٍ لتحديد السيناريو القادم.\n"

        options_text = get_options(symbol, price, supports, resistances)

        return f"""
📊 تحليل {symbol}

━━━━━━━━━━━━━━━━━━
💰 السعر: ${price:.2f}
📅 التغير: {daily_change}
📈 الاتجاه: {trend}
━━━━━━━━━━━━━━━━━━
📊 RSI: {rsi_value:.1f} ({rsi_status})
📉 MACD: {macd_status}
━━━━━━━━━━━━━━━━━━
📏 MA20: ${ma20:.2f}
📏 MA50: ${ma50:.2f}
━━━━━━━━━━━━━━━━━━
🎯 أعلى 30 يوم: ${high30:.2f}
🎯 أدنى 30 يوم: ${low30:.2f}
━━━━━━━━━━━━━━━━━━
🛡️ الدعوم:
{support_text}
🚧 المقاومات:
{resistance_text}
━━━━━━━━━━━━━━━━━━
{scenario}
━━━━━━━━━━━━━━━━━━
🔔 الإشارة: {final_signal}
⭐ القوة: {score}/5
━━━━━━━━━━━━━━━━━━
{options_text}
━━━━━━━━━━━━━━━━━━
⚠️ تحليل آلي وليس توصية مالية.
"""
    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {e}")
        return None

# ============================================================
# أوامر بوت تيليجرام
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً بك! البوت جاهز الآن. أرسل لي رمز أي سهم (مثل AAPL أو TSLA) وسأقوم بتحليله لك فوراً."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = update.message.text.strip()
    
    # رسالة مؤقتة لتوضيح أن البوت يعمل
    wait_msg = await update.message.reply_text(f"🔍 جاري جلب وتحليل بيانات السهم `{symbol}`...")

    result = analyze_stock(symbol)
    
    if result:
        await wait_msg.edit_text(result)
    else:
        await wait_msg.edit_text(f"❌ عذراً، لم أتمكن من العثور على بيانات للسهم `{symbol}` أو أن الرمز غير صحيح.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("🤖 البوت يعمل الآن ويستمع للرسائل بنجاح...")
    app.run_polling()

if __name__ == "__main__":
    main()
