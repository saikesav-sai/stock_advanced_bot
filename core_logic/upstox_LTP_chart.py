import threading
import upstox_client
import os
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque

load_dotenv()

prices = deque(maxlen=200)
latest_price = None

# YOUR IRFC SYMBOL (from your output)
SYMBOLS = os.getenv("SYMBOLS")

def on_message(msg):
    global latest_price

    try:
        feeds = msg.get("feeds", {})

        if SYMBOLS in feeds:
            # Correct path for EQUITY STOCKS (from your IRFC feed)
            latest_price = feeds[SYMBOLS]["fullFeed"]["marketFF"]["ltpc"]["ltp"]
            # print("price:", latest_price)

    except Exception as e:
        print("Error:", e)


def start_streamer():
    configuration = upstox_client.Configuration()
    configuration.access_token = os.getenv("UPSTOX_ACCESS_TOKEN")

    streamer = upstox_client.MarketDataStreamerV3(
        upstox_client.ApiClient(configuration),
        [SYMBOLS],
        "full"
    )

    streamer.on("message", on_message)
    streamer.connect()


def update_graph(i):
    if latest_price is not None:
        prices.append(latest_price)

    plt.cla()

    if len(prices) > 0:
        plt.plot(prices, label=SYMBOLS)

        # Mark last price with red dot
        plt.scatter(len(prices)-1, prices[-1], color='red', s=60)

        # Show live price as text
        plt.text(
            len(prices)-1,
            prices[-1],
            f"  {prices[-1]}",
            fontsize=12,
            color='red'
        )

    plt.title(f"Live Price: {SYMBOLS}")
    plt.xlabel("Last 200 Points")
    plt.ylabel("Price")
    plt.legend(loc="upper left")


def main():
    thread = threading.Thread(target=start_streamer, daemon=True)
    thread.start()

    ani = animation.FuncAnimation(plt.gcf(), update_graph, interval=1000)
    plt.show()


if __name__ == "__main__":
    main()
