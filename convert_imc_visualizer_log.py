import json
import sys
from collections import defaultdict
from pathlib import Path


def parse_activity_rows(activities_log: str):
    lines = [line for line in activities_log.strip().splitlines() if line.strip()]
    if not lines:
        raise ValueError("activitiesLog is empty")

    header = lines[0]
    rows = []
    for line in lines[1:]:
        columns = line.split(";")
        rows.append(
            {
                "day": int(columns[0]),
                "timestamp": int(columns[1]),
                "product": columns[2],
                "buy_orders": parse_order_levels(columns, [(3, 4), (5, 6), (7, 8)]),
                "sell_orders": parse_order_levels(columns, [(9, 10), (11, 12), (13, 14)], sells=True),
            }
        )

    return header, rows


def parse_order_levels(columns, pairs, sells=False):
    orders = {}
    for price_idx, volume_idx in pairs:
        if columns[price_idx] == "" or columns[volume_idx] == "":
            continue
        price = int(float(columns[price_idx]))
        volume = int(float(columns[volume_idx]))
        orders[price] = -abs(volume) if sells else abs(volume)
    return orders


def build_trade_index(trade_history):
    trades_by_timestamp = defaultdict(lambda: defaultdict(list))
    positions = defaultdict(int)

    for trade in sorted(trade_history, key=lambda trade: trade["timestamp"]):
        timestamp = int(trade["timestamp"])
        symbol = trade["symbol"]
        trade_row = [
            symbol,
            float(trade["price"]),
            int(trade["quantity"]),
            trade.get("buyer", ""),
            trade.get("seller", ""),
            timestamp,
        ]

        is_submission_buy = trade.get("buyer") == "SUBMISSION"
        is_submission_sell = trade.get("seller") == "SUBMISSION"

        if is_submission_buy or is_submission_sell:
            trades_by_timestamp[timestamp][symbol].append(trade_row)

            signed_quantity = int(trade["quantity"])
            if is_submission_buy:
                positions[symbol] += signed_quantity
            else:
                positions[symbol] -= signed_quantity

    return trades_by_timestamp, positions


def group_books_by_timestamp(activity_rows):
    grouped = defaultdict(dict)
    products = set()

    for row in activity_rows:
        grouped[row["timestamp"]][row["product"]] = row
        products.add(row["product"])

    return grouped, sorted(products)


def cumulative_positions_by_timestamp(timestamps, trades_by_timestamp):
    current = defaultdict(int)
    snapshots = {}

    for timestamp in timestamps:
        for symbol, trades in trades_by_timestamp.get(timestamp, {}).items():
            for trade in trades:
                quantity = int(trade[2])
                if trade[3] == "SUBMISSION":
                    current[symbol] += quantity
                elif trade[4] == "SUBMISSION":
                    current[symbol] -= quantity
        snapshots[timestamp] = dict(current)

    return snapshots


def build_visualizer_rows(activity_rows, trade_history):
    books_by_timestamp, products = group_books_by_timestamp(activity_rows)
    timestamps = sorted(books_by_timestamp.keys())
    own_trades_by_timestamp, _ = build_trade_index(trade_history)
    positions_by_timestamp = cumulative_positions_by_timestamp(timestamps, own_trades_by_timestamp)

    listings = [[product, product, "XIRECS"] for product in products]
    observations = [{}, {}]

    rows = []
    for timestamp in timestamps:
        order_depths = {}
        for product in products:
            row = books_by_timestamp[timestamp].get(product)
            if row is None:
                continue
            order_depths[product] = [row["buy_orders"], row["sell_orders"]]

        own_trades = []
        for product in products:
            own_trades.extend(own_trades_by_timestamp.get(timestamp, {}).get(product, []))

        state = [
            timestamp,
            "",
            listings,
            order_depths,
            own_trades,
            [],
            positions_by_timestamp[timestamp],
            observations,
        ]
        rows.append([state, [], 0, "", ""])

    return rows


def build_output_text(activities_log: str, compressed_rows):
    lines = ["Activities log:", activities_log.strip(), "", "Sandbox logs:"]

    for row in compressed_rows:
        row_json = json.dumps(row, separators=(",", ":"))
        lines.append('  "sandboxLog": "",')
        lines.append(f'  "lambdaLog": {json.dumps(row_json)},')

    return "\n".join(lines) + "\n"


def load_source(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python3 convert_imc_visualizer_log.py <input.json-or-log> [output.log]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = (
        Path(sys.argv[2])
        if len(sys.argv) == 3
        else input_path.with_name(f"{input_path.stem}_visualizer.log")
    )

    source = load_source(input_path)
    if "activitiesLog" not in source:
        raise ValueError("Input file does not contain activitiesLog")

    activities_log = source["activitiesLog"]
    trade_history = source.get("tradeHistory", [])

    _, activity_rows = parse_activity_rows(activities_log)
    compressed_rows = build_visualizer_rows(activity_rows, trade_history)
    output_text = build_output_text(activities_log, compressed_rows)

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(output_text)

    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
