import logging
import pandas as pd
import numpy as np
import yfinance as yf
from telegram import Update, ReplyKeyboardMarkup
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

# قاموس مؤقت لتخزين حالة كل مستخدم (هل ضغط زر تحليل أو زر أرباح)
user_states = {}

# ============================================================
# الدوال المساعدة للتحليل الفني والأرباح والأوبشن
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

def get_options_data(ticker, price):
    try:
        options_dates = ticker.options
        if options_dates:
            expiry = options_dates[0]
            opt_chain = ticker.option_chain(expiry)
            calls = opt_chain.calls
            puts = opt_chain.puts
            itm_calls = calls[calls['strike'] > price]
            call_text = f"🟢 Call | Strike: ${itm_calls.iloc[0]['strike']} | Ask: ${itm_calls.iloc[0].get('ask', 0)}" if not itm_calls.empty else "🟢 Call | غير متوفر"
            itm_puts = puts[puts['strike'] < price]
            put_text = f"🔴 Put | Strike: ${itm_puts.iloc[-1]['strike']} | Ask: ${itm_puts.iloc[-1].get('ask', 0)}" if not itm_puts.empty else "🔴 Put | غير متوفر"
            return f"📊 **عقود الخيارات (تاريخ: {expiry}):**\n{call_text}\n{put_text}"
    except Exception:
        pass
    return "📊 عقود الخيارات: غير متوفرة حالياً."

def get_earnings_full(symbol):
    try:
        ticker = yf.Ticker(symbol)
        calendar = ticker.calendar
        next_earnings_date = "غير متوفر"
        if calendar is not None and not isinstance(calendar, dict):
            try:
                if 'Earnings Date' in calendar and len(calendar['Earnings Date']) > 0:
                    next_earnings_date = str(calendar['Earnings Date'][0]).split()[0]
            except:
                pass
        elif isinstance(calendar, dict):
            if 'Earnings Date' in calendar and len(calendar['Earnings Date']) > 0:
                next_earnings_date = str(calendar['Earnings Date'][0]).split()[0]

        q_earnings = ticker.quarterly_earnings
        earnings_history = ""
        if q_earnings is not None and not q_earnings.empty:
            last_4 = q_earnings.tail(4)
            earnings_history = "📈 **آخر أرباح للشركة (آخر 4 أرباع):**\n"
            for idx, row in last_4.iterrows():
                rev = row.get('Revenue', 'N/A')
                earnings_history += f"• {str(idx)[:10]} | الإيرادات: {rev:,} $\n" if isinstance(rev, (int, float)) else f"• {str(idx)[:10]} | البيانات متاحة\n"
        else:
            earnings_history = "📈 آخر أرباح للشركة: غير متوفرة حالياً."

        return f"""
📑 **تقرير أرباح الشركة لـ {symbol}**

📅 **موعد الأرباح القادم:** {next_earnings_date}

{earnings_history}
"""
    except Exception as e:
        logger.error(f"Error fetching earnings for {symbol}: {e}")
        return f"❌ حدث خطأ أثناء جلب أرباح الشركة `{symbol}`."

# ============================================================
# دالة تحليل السهم الشاملة
# ============================================================

def analyze_stock(symbol):
    symbol = symbol.upper().strip()
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="6mo", interval="1d")
        if data.empty or len(data) < 50:
            return None

        close = data["Close"]
        price = float(close.iloc[-1])
        previous = float(close.iloc[-2])
        change = ((price - previous) / previous) * 100

        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1])

        rsi = calculate_rsi(close)
        rsi_value = float(rsi.iloc[-1])
        rsi_status = "🟢 تشبع بيع" if rsi_value < 30 else ("🔴 تشبع شراء" if rsi_value > 70 else "⚪ طبيعي")

        macd, signal = calculate_macd(close)
        macd_value, signal_value = float(macd.iloc[-1]), float(signal.iloc[-1])
        macd_status = "🟢 إيجابي" if macd_value > signal_value else "🔴 سلبي"

        high30 = float(data["High"].tail(30).max())
        low30 = float(data["Low"].tail(30).min())
        trend = "🟢 صاعد" if price > ma20 > ma50 else ("🔴 هابط" if price < ma20 < ma50 else "🟡 متذبذب")

        supports, resistances = get_support_resistance(data, price)
        score = sum([price > ma20, ma20 > ma50, macd_value > signal_value, 30 <= rsi_value <= 70, price > high30 * 0.97])

        final_signal = "🟢 إيجابية" if score >= 4 else ("🔴 سلبية" if score <= 1 else "🟡 محايدة")
        daily_change = f"🟢 +{change:.2f}%" if change > 0 else (f"🔴 {change:.2f}%" if change < 0 else "⚪ 0.00%")

        support_text = "".join([f"{i}️⃣ ${lvl:.2f} ({(lvl - price) / price * 100:.2f}%)\n" for i, lvl in enumerate(supports, start=1)]) if supports else "❌ لا يوجد دعم واضح.\n"
        resistance_text = "".join([f"{i}️⃣ ${lvl:.2f} (+{(lvl - price) / price * 100:.2f}%)\n" for i, lvl in enumerate(resistances, start=1)]) if resistances else "❌ لا يوجد مقاومة واضحة.\n"

        options_text = get_options_data(ticker, price)

        return f"""
📊 تحليل السهم: {symbol}
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
# واجهة الأزرار وأوامر البوت
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["📊 تحليل سهم", "💰 الأرباح"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "أهلاً بك! استخدم الأزرار بالأسفل للتحكم:",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    
    # 1. إذا ضغط المستخدم على زر "📊 تحليل سهم"
    if text == "📊 تحليل سهم":
        user_states[user_id] = "WAITING_FOR_STOCK"
        await update.message.reply_text("📥 حسناً، أرسل الآن رمز السهم الذي تريد تحليله (مثل: AAPL):")
        return

    # 2. إذا ضغط المستخدم على زر "💰 الأرباح"
    elif text == "💰 الأرباح":
        user_states[user_id] = "WAITING_FOR_EARNINGS"
        await update.message.reply_text("📥 حسناً، أرسل رمز السهم متبوعاً بحرف E (مثل: AAPL E) لعرض الأرباح:")
        return

    # 3. معالجة الرمز بناءً على الزر الذي تم ضغطه سابقاً أو الكتابة المباشرة
    current_state = user_states.get(user_id)

    # إذا كان في وضع تحليل السهم أو كتب الرمز مباشرة
    if current_state == "WAITING_FOR_STOCK" or (text.isalpha() and len(text) <= 5):
        symbol = text.upper()
        user_states[user_id] = None # إعادة تعيين الحالة
        wait_msg = await update.message.reply_text(f"🔍 جاري تحليل السهم `{symbol}` مع عقود الخيارات...")
        result = analyze_stock(symbol)
        if result:
            await wait_msg.edit_text(result)
        else:
            await wait_msg.edit_text(f"❌ عذراً، لم أتمكن من العثور على بيانات للسهم `{symbol}`.")

    # إذا كان في وضع الأرباح أو كتب الرمز منتهي بـ E
    elif current_state == "WAITING_FOR_EARNINGS" or text.upper().endswith("E"):
        clean_text = text.upper().replace("E", "").strip()
        user_states[user_id] = None # إعادة تعيين الحالة
        wait_msg = await update.message.reply_text(f"⏳ جاري جلب أرباح الشركة `{clean_text}`...")
        result = get_earnings_full(clean_text)
        await wait_msg.edit_text(result)
        
    else:
        await update.message.reply_text("⚠️ يرجى الضغط على إحدى الأزرار بالأسفل (📊 تحليل سهم أو 💰 الأرباح) ثم إرسال رمز السهم.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("🤖 البوت يعمل بكامل الأزرار والشروط الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()
