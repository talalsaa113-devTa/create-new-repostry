# ============================================================
# تحليل السهم - شامل
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

        # ====================================================
        # RSI
        # ====================================================

        rsi = calculate_rsi(close)
        rsi_value = float(rsi.iloc[-1])

        if rsi_value < 30:
            rsi_status = "🟢 تشبع بيع"
        elif rsi_value > 70:
            rsi_status = "🔴 تشبع شراء"
        else:
            rsi_status = "⚪ طبيعي"

        # ====================================================
        # MACD
        # ====================================================

        macd, signal = calculate_macd(close)

        macd_value = float(macd.iloc[-1])
        signal_value = float(signal.iloc[-1])

        if macd_value > signal_value:
            macd_status = "🟢 إيجابي"
        else:
            macd_status = "🔴 سلبي"

        # ====================================================
        # أعلى وأدنى 30 يوم
        # ====================================================

        high30 = float(
            data["High"].tail(30).max()
        )

        low30 = float(
            data["Low"].tail(30).min()
        )

        # ====================================================
        # الاتجاه
        # ====================================================

        if price > ma20 > ma50:
            trend = "🟢 صاعد"

        elif price < ma20 < ma50:
            trend = "🔴 هابط"

        else:
            trend = "🟡 متذبذب"

        # ====================================================
        # الدعم والمقاومة
        # ====================================================

        supports, resistances = get_support_resistance(
            data,
            price
        )

        # ====================================================
        # الإشارة
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

        if price > high30 * 0.97:
            score += 1

        if score >= 4:
            final_signal = "🟢 إيجابية"

        elif score <= 1:
            final_signal = "🔴 سلبية"

        else:
            final_signal = "🟡 محايدة"

        # ====================================================
        # التغير اليومي
        # ====================================================

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

            nearest_support = supports[0]

        else:

            support_text = (
                "❌ لا يوجد مستوى دعم واضح.\n"
            )

            nearest_support = None

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

            nearest_resistance = resistances[0]

        else:

            resistance_text = (
                "❌ لا يوجد مستوى مقاومة واضح.\n"
            )

            nearest_resistance = None

        # ====================================================
        # السيناريو القادم
        # ====================================================

        scenario = ""

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

                if len(resistances) > 1:

                    next_target = resistances[1]

                    scenario = f"""
🟢 السيناريو الأقرب:

اختراق المقاومة:
${nearest_resistance:.2f}

🎯 الهدف التالي:
${next_target:.2f}
"""

                else:

                    scenario = f"""
🟢 السيناريو الأقرب:

اختراق المقاومة:
${nearest_resistance:.2f}

🎯 قد يستهدف السهم مستويات أعلى.
"""

            elif trend == "🔴 هابط":

                if len(supports) > 1:

                    next_target = supports[1]

                    scenario = f"""
🔴 السيناريو الأقرب:

كسر الدعم:
${nearest_support:.2f}

🎯 الهدف التالي:
${next_target:.2f}
"""

                else:

                    scenario = f"""
🔴 السيناريو الأقرب:

كسر الدعم:
${nearest_support:.2f}

🎯 قد يبحث السهم عن دعم أدنى.
"""

            else:

                if resistance_distance < abs(
                    support_distance
                ):

                    scenario = f"""
🟡 السيناريو الأقرب:

🚧 المقاومة:
${nearest_resistance:.2f}

🛡️ الدعم:
${nearest_support:.2f}

راقب الاختراق أو الكسر قبل اتخاذ القرار.
"""

                else:

                    scenario = f"""
🟡 السيناريو الأقرب:

🛡️ الدعم:
${nearest_support:.2f}

🚧 المقاومة:
${nearest_resistance:.2f}

راقب الارتداد أو الكسر قبل اتخاذ القرار.
"""

        else:

            scenario = """
🟡 لا يوجد مستوى واضح كافٍ
لتحديد السيناريو القادم.
"""

        # ====================================================
        # الخيارات
        # ====================================================

        print(
            f"📑 جاري جلب خيارات {symbol}..."
        )

        options_text = get_options(
            symbol,
            price,
            supports,
            resistances
        )

        # ====================================================
        # النتيجة النهائية
        # ====================================================

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

{options_text}

━━━━━━━━━━━━━━━━━━

⚠️ تحليل آلي وليس توصية مالية.
⚠️ عقود الخيارات عالية المخاطر وقد تخسر كامل قيمة الـ Premium.
"""
