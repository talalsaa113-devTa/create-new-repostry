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
                if 'Earnings Date' in calendar:
                    dates = calendar['Earnings Date']
                    if len(dates) > 0:
                        next_earnings_date = str(dates[0]).split()[0]
            except:
                pass
        elif isinstance(calendar, dict):
            if 'Earnings Date' in calendar:
                dates = calendar['Earnings Date']
                if len(dates) > 0:
                    next_earnings_date = str(dates[0]).split()[0]

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

def get_earnings_note(symbol):
    # خيار حرف N (معلومات أو ملاحظات الأرباح السريعة)
    try:
        ticker = yf.Ticker(symbol)
        calendar = ticker.calendar
        next_date = "غير متوفر"
        if calendar is not None and not isinstance(calendar, dict):
            if 'Earnings Date' in calendar and len(calendar['Earnings Date']) > 0:
                next_date = str(calendar['Earnings Date'][0]).split()[0]
        elif isinstance(calendar, dict):
            if 'Earnings Date' in calendar and len(calendar['Earnings Date']) > 0:
                next_date = str(calendar['Earnings Date'][0]).split()[0]
                
        return f"📌 **ملاحظة أرباح `{symbol}`:**\n📅 موعد الإعلان القادم المتوقع: `{next_date}`\n💡 أرسل `{symbol}E` لعرض تفاصيل آخر 4 أرباع."
    except Exception:
        return f"📌 ملاحظة أرباح `{symbol}` غير متوفرة حالياً."

# ============================================================
# دالة تحليل السهم الشاملة (وتحتوي على الأوبشن)
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

        score = 0
        if price > ma20: score += 1
        if ma20 > ma50: score += 1
        if macd_value > signal_value: score += 1
        if 30 <= rsi_value <= 70: score += 1
        if price > high30 * 0.97: score += 1

        final_signal = "🟢 إيجابية" if score >= 4 else ("🔴 سلبية" if score <= 1 else "🟡 محايدة")
        daily_change = f"🟢 +{change:.2f}%" if change > 0 else (f"🔴 {change:.2f}%" if change < 0 else "⚪ 0.00%")

        support_text = "".join([f"{i}️⃣ ${lvl:.2f} ({(lvl - price) / price * 100:.2f}%)\n" for i, lvl in enumerate(supports, start=1)]) if supports else "❌ لا يوجد دعم واضح.\n"
        resistance_text = "".join([f"{i}️⃣ ${lvl:.2f} (+{(lvl - price) / price * 100:.2f}%)\n" for i, lvl in enumerate(resistances, start=1)]) if resistances else "❌ لا يوجد مقاومة واضحة.\n"

        # الأوبشن متضمن داخل التحليل
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
# معالج الرسائل الموجه حسب الشروط المطلوبة
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً بك! استخدم الأوامر التالية:\n"
        "• أرسل **رمز السهم فقط** (مثل `AAPL`) لتحليل السهم مع الأوبشن.\n"
        "• أرسل **رمز السهم + E** (مثل `AAPL E`) لعرض أرباح الشركة (آخر 4 أرباع والموعد القادم).\n"
        "• أرسل **رمز السهم + N** (مثل `AAPL N`) لعرض ملاحظة الأرباح المختصرة."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    
    # 1. إذا انتهى بـ E (أرباح الشركة الشاملة: اسم السهم + E)
    if text.endswith("E") and len(text) > 1:
        symbol = text[:-1].strip()
        wait_msg = await update.message.reply_text(f"⏳ جاري جلب بيانات أرباح الشركة `{symbol}`...")
        result = get_earnings_full(symbol)
        await wait_msg.edit_text(result)
        
    # 2. إذا انتهى بـ N (أرباح الشركة المختصرة: اسم السهم + N)
    elif text.endswith("N") and len(text) > 1:
        symbol = text[:-1].strip()
        wait_msg = await update.message.reply_text(f"⏳ جاري جلب ملخص أرباح `{symbol}`...")
        result = get_earnings_note(symbol)
        await wait_msg.edit_text(result)
        
    # 3. إذا كان اسم السهم العادي فقط (تحليل الأسهم + الأوبشن)
    elif text.isalpha() and len(text) <= 5:
        symbol = text
        wait_msg = await update.message.reply_text(f"🔍 جاري تحليل السهم `{symbol}` مع عقود الخيارات...")
        result = analyze_stock(symbol)
        if result:
            await wait_msg.edit_text(result)
        else:
            await wait_msg.edit_text(f"❌ عذراً، لم أتمكن من العثور على بيانات للسهم `{symbol}` أو الرمز غير صحيح.")
            
    # 4. غير ذلك (يتم تجاهله أو تنبيه المستخدم)
    else:
        await update.message.reply_text("⚠️ صيغة غير صحيحة.\n• للتحليل + الأوبشن: أرسل رمز السهم فقط (مثل `AAPL`).\n• للأرباح: أرسل الرمز متبوعاً بحرف E (مثل `AAPL E`).\n• للملاحظات: أرسل الرمز متبوعاً بحرف N (مثل `AAPL N`).")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("🤖 البوت يعمل بالصيغ المحددة بنجاح...")
    app.run_polling()

if __name__ == "__main__":
    main()
