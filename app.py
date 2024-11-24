import streamlit as st
import json
import websocket
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from mplfinance.original_flavor import candlestick_ohlc
from matplotlib.dates import date2num
from datetime import datetime
from threading import Thread

# Define WebSocket URL and other constants
COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"
product_ids = ["ETH-USD"]
MAX_ROWS = 60000
period = 15000
columns = ["time", "product_id", "price", "shares", "side"]
market_data = pd.DataFrame(columns=columns)

# Coinbase WebSocket class
class CoinbaseWebSocket(Thread):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.ws = None

    def on_open(self, ws):
        print("WebSocket connection opened.")
        subscribe_message = {
            "type": "subscribe",
            "channels": [{"name": "ticker", "product_ids": product_ids}]
        }
        ws.send(json.dumps(subscribe_message))

    def on_message(self, ws, message):
        global market_data
        data = json.loads(message)

        if data.get('type') == 'ticker':
            time = data.get("time")
            product_id = data.get("product_id")
            side = data.get("side")
            price = data.get("price")
            shares = data.get("last_size")

            if price and shares:
                new_row = {
                    "time": pd.to_datetime(time),
                    "product_id": product_id,
                    "price": float(price),
                    "shares": float(shares),
                    "side": side
                }
                market_data = pd.concat(
                    [market_data, pd.DataFrame([new_row])], ignore_index=True
                )

                # Keep only the last MAX_ROWS rows
                if len(market_data) > MAX_ROWS:
                    market_data = market_data.tail(MAX_ROWS).reset_index(drop=True)

    def on_error(self, ws, error):
        print(f"Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("WebSocket connection closed.")

    def run(self):
        self.ws = websocket.WebSocketApp(
            self.url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        self.ws.run_forever()

    def stop(self):
        if self.ws:
            self.ws.close()

def calculate_pivot(data, period):
    pivot_point = (data['price'].tail(period).max() + data['price'].tail(period).min() + data['price'].tail(period).iloc[-1]) / 3
    return pivot_point

def calculate_resistance1(pivot, data, period):
    resistance1 = (pivot*2) - data['price'].tail(period).min()
    return resistance1

def calculate_resistance2(pivot, data, period):
    resistance2 = (pivot + (data['price'].tail(period).max() - data['price'].tail(period).min()))
    return resistance2

def calculate_support1(pivot, data, period):
    support1 = (pivot*2) - data['price'].tail(period).max()
    return support1

def calculate_support2(pivot, data, period):
    support2 = (pivot - (data['price'].tail(period).max() - data['price'].tail(period).min()))
    return support2


# Streamlit UI setup
st.title("Real-Time ETH Chart")

# Placeholder for the plot
chart_placeholder = st.empty()

# Start the WebSocket in a background thread
def start_websocket():
    ws_thread = CoinbaseWebSocket(COINBASE_WS_URL)
    ws_thread.start()
    return ws_thread

# Plotting function for Streamlit
def plot_graph():
    global market_data

    if not market_data.empty:
        # Group data into 15-second intervals
        market_data["time"] = pd.to_datetime(market_data["time"])
        ohlc_data = (
            market_data
            .set_index("time")
            .resample("15S")  # Resample to 15-second intervals
            .agg({
                "price": ["first", "max", "min", "last"],  # Open, High, Low, Close
                "shares": "sum"
            })
        )
        ohlc_data.columns = ["open", "high", "low", "close", "volume"]
        ohlc_data = ohlc_data.dropna()

        if not ohlc_data.empty:
            ohlc_data.reset_index(inplace=True)
            ohlc_data["time"] = ohlc_data["time"].map(date2num)

            pivot = calculate_pivot(market_data)
            r1 = calculate_resistance1(pivot, market_data)
            s1 = calculate_support1(pivot, market_data)
            r2 = calculate_resistance2(pivot, market_data)
            s2 = calculate_support2(pivot, market_data)

            ohlc_data["cumulative_price_volume"] = (ohlc_data["close"] * ohlc_data["volume"]).cumsum()
            ohlc_data["cumulative_volume"] = ohlc_data["volume"].cumsum()
            ohlc_data["VWAP"] = ohlc_data["cumulative_price_volume"] / ohlc_data["cumulative_volume"]

            # Prepare the plot
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.set_facecolor("#2E2E2E")
            candlestick_ohlc(
                ax,
                ohlc_data[["time", "open", "high", "low", "close"]].values,
                width=0.6 / (24 * 60 * 60),  # Width of candlesticks (in days)
                colorup="green",
                colordown="red"
            )

            ax.axhline(pivot, color='white', linestyle='-', linewidth=1, label="Pivot Point")
            ax.axhline(r1, color='#ff5e41', linestyle='-', linewidth=2, label="Resistance 1")
            ax.axhline(s1, color='#53fc1d', linestyle='-', linewidth=2, label="Support 1")
            ax.axhline(r2, color='#c21d00', linestyle='-', linewidth=2, label="Resistance 2")
            ax.axhline(s2, color='#207e02', linestyle='-', linewidth=2, label="Support 2")

            ax1.plot(ohlc_data["time"], ohlc_data["VWAP"], label="VWAP", color="purple", linewidth=1.5, linestyle="-")

            ax.text(x=ohlc_data["time"].iloc[0], y=r1, s=f'{r1:.2f}', color='white', fontsize=10, va='center',
                     ha='left', bbox=dict(boxstyle='round,pad=0.3', edgecolor='blue', facecolor='#2E2E2E'))
            ax.text(x=ohlc_data["time"].iloc[0], y=s1, s=f'{s1:.2f}', color='white', fontsize=10, va='center',
                     ha='left', bbox=dict(boxstyle='round,pad=0.3', edgecolor='blue', facecolor='#2E2E2E'))
            ax.text(x=ohlc_data["time"].iloc[0], y=pivot, s=f'{pivot:.2f}', color='white', fontsize=10, va='center',
                     ha='left', bbox=dict(boxstyle='round,pad=0.3', edgecolor='blue', facecolor='#2E2E2E'))

            ax.set_xlabel("Time", fontsize=10, color="black")
            ax.set_ylabel("Price (USD)", fontsize=10, color="black")
            #ax.set_ylabel("Volume", fontsize=10, color="white")
            ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%H:%M:%S"))
            plt.xticks(rotation=45, color="white")

            # Update the chart in the placeholder
            chart_placeholder.pyplot(fig)

# Run the WebSocket and graph update
def main():
    # Start the WebSocket connection in the background thread
    ws_thread = start_websocket()

    # Update the plot every 1 second using Streamlit
    while True:
        plot_graph()

# Start the main function in Streamlit
if __name__ == "__main__":
    main()
