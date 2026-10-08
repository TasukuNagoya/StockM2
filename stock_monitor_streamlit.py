import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Stock Mon", page_icon="📈", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "stocks.json"


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    # Streamlit Community Cloud上のローカル保存は永続保証されません。
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)


@st.cache_data(ttl=30, show_spinner=False)
def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period="5d", interval="1d")
        if data.empty:
            return None

        current_price = float(data["Close"].iloc[-1])
        previous_close = (
            float(data["Close"].iloc[-2]) if len(data) >= 2 else current_price
        )
        change = current_price - previous_close
        change_percent = (change / previous_close * 100) if previous_close else 0.0

        return {
            "price": current_price,
            "previous_close": previous_close,
            "change": change,
            "change_percent": change_percent,
        }
    except Exception:
        return None


def fetch_prices(stocks):
    rows = []
    for stock in stocks:
        code = str(stock["code"]).strip()
        name = stock.get("name", "")
        min_price = float(stock["min"])
        max_price = float(stock["max"])
        data = get_stock_data(code)

        if data is None:
            rows.append({
                "銘柄コード": code,
                "銘柄名": name,
                "現在値": None,
                "前日比": None,
                "騰落率(%)": None,
                "最小値": min_price,
                "最大値": max_price,
                "状態": "取得失敗",
            })
            continue

        price = data["price"]
        if price < min_price:
            status = "▼ 下限割れ"
        elif price > max_price:
            status = "▲ 上限超え"
        else:
            status = "正常"

        rows.append({
            "銘柄コード": code,
            "銘柄名": name,
            "現在値": price,
            "前日比": data["change"],
            "騰落率(%)": data["change_percent"],
            "最小値": min_price,
            "最大値": max_price,
            "状態": status,
        })
    return pd.DataFrame(rows)


def color_alerts(row):
    if row["状態"] in ("▼ 下限割れ", "▲ 上限超え", "取得失敗"):
        return ["color: red; font-weight: bold"] * len(row)
    return [""] * len(row)


if "config" not in st.session_state:
    try:
        st.session_state.config = load_config()
    except Exception as e:
        st.error(f"stocks.json を読み込めません: {e}")
        st.stop()

config = st.session_state.config
stocks = config.get("stocks", [])
refresh_seconds = int(config.get("refresh_seconds", 60))

st.title("📈 Stock Mon")
st.caption("Yahoo Finance (yfinance) から株価を取得します。")

left, right = st.columns([1, 3])
with left:
    if st.button("🔄 今すぐ更新", use_container_width=True):
        get_stock_data.clear()
        st.rerun()
with right:
    st.write(f"設定上の更新間隔: **{refresh_seconds} 秒**")

st.subheader("On-Going Stock")

# Streamlit 1.37+ の fragment 自動更新。
@st.fragment(run_every=f"{max(refresh_seconds, 10)}s")
def price_panel():
    df = fetch_prices(st.session_state.config.get("stocks", []))

    def fmt_num(x):
        return "" if pd.isna(x) else f"{x:,.2f}"

    display = df.copy()
    for col in ["現在値", "前日比", "最小値", "最大値"]:
        display[col] = display[col].map(fmt_num)
    display["騰落率(%)"] = display["騰落率(%)"].map(
        lambda x: "" if pd.isna(x) else f"{x:+.2f}%"
    )

    st.dataframe(
        display.style.apply(color_alerts, axis=1),
        use_container_width=True,
        hide_index=True,
    )
    st.caption("最終更新: " + datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

price_panel()

st.divider()
st.subheader("⚙️ 銘柄・上下限設定")
st.write("表を直接編集できます。銘柄の追加・削除も可能です。")

edit_df = pd.DataFrame(stocks, columns=["code", "name", "min", "max"])
edited = st.data_editor(
    edit_df,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "code": st.column_config.TextColumn("銘柄コード", required=True),
        "name": st.column_config.TextColumn("銘柄名"),
        "min": st.column_config.NumberColumn("最小値", format="%.2f", required=True),
        "max": st.column_config.NumberColumn("最大値", format="%.2f", required=True),
    },
)

c1, c2, c3 = st.columns(3)

with c1:
    if st.button("💾 設定を保存", type="primary", use_container_width=True):
        new_stocks = edited.to_dict("records")
        invalid = [
            s for s in new_stocks
            if not str(s.get("code", "")).strip()
            or pd.isna(s.get("min"))
            or pd.isna(s.get("max"))
            or float(s["min"]) > float(s["max"])
        ]
        if invalid:
            st.error("銘柄コード、最小値・最大値を確認してください。最小値は最大値以下にしてください。")
        else:
            clean = []
            for s in new_stocks:
                clean.append({
                    "code": str(s["code"]).strip(),
                    "name": "" if pd.isna(s.get("name")) else str(s.get("name", "")),
                    "min": float(s["min"]),
                    "max": float(s["max"]),
                })
            config["stocks"] = clean
            st.session_state.config = config
            try:
                save_config(config)
                get_stock_data.clear()
                st.success("設定を保存しました。")
            except Exception as e:
                st.warning(f"画面上の設定は更新しましたが、JSON保存に失敗しました: {e}")
            st.rerun()

with c2:
    config_json = json.dumps(
        {"refresh_seconds": refresh_seconds, "stocks": edited.to_dict("records")},
        ensure_ascii=False, indent=4
    )
    st.download_button(
        "⬇️ stocks.json を保存",
        data=config_json,
        file_name="stocks.json",
        mime="application/json",
        use_container_width=True,
    )

with c3:
    uploaded = st.file_uploader("stocks.json を読込", type=["json"], label_visibility="collapsed")
    if uploaded is not None:
        try:
            new_config = json.load(uploaded)
            st.session_state.config = new_config
            get_stock_data.clear()
            st.success("JSONを読み込みました。")
            st.rerun()
        except Exception as e:
            st.error(f"JSONの読込に失敗しました: {e}")

st.info(
    "Streamlit Community Cloudでは、アプリからサーバー上の stocks.json を変更しても "
    "再起動・再デプロイ時に元へ戻る可能性があります。長期保存したい設定は "
    "「stocks.json を保存」で手元に保存し、GitHub側のJSONを更新する運用が確実です。"
)
