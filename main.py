from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState
from typing import Any, Dict, List
import json

POSITION_LIMITS = {
    "EMERALDS": 80,
    "TOMATOES": 80,
}

EMERALDS_FAIR_VALUE = 10000

TOMATOES_FAIR_VALUE = 4989
TOMATOES_LATE_GENTLE_TIMESTAMP = 194000
TOMATOES_LATE_GENTLE_POSITION = 45
TOMATOES_LATE_GENTLE_SIZE = 6


class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(
        self,
        state: TradingState,
        orders: dict[Symbol, list[Order]],
        conversions: int,
        trader_data: str,
    ) -> None:
        base_length = len(
            self.to_json(
                [
                    self.compress_state(state, ""),
                    self.compress_orders(orders),
                    conversions,
                    "",
                    "",
                ]
            )
        )

        # Keep trader data and logs within the simulator's line-length limit.
        max_item_length = (self.max_log_length - base_length) // 3

        print(
            self.to_json(
                [
                    self.compress_state(state, self.truncate(state.traderData, max_item_length)),
                    self.compress_orders(orders),
                    conversions,
                    self.truncate(trader_data, max_item_length),
                    self.truncate(self.logs, max_item_length),
                ]
            )
        )

        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        compressed = []
        for listing in listings.values():
            compressed.append([listing.symbol, listing.product, listing.denomination])
        return compressed

    def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        compressed = {}
        for symbol, order_depth in order_depths.items():
            compressed[symbol] = [order_depth.buy_orders, order_depth.sell_orders]
        return compressed

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
        compressed = []
        for arr in trades.values():
            for trade in arr:
                compressed.append(
                    [
                        trade.symbol,
                        trade.price,
                        trade.quantity,
                        trade.buyer,
                        trade.seller,
                        trade.timestamp,
                    ]
                )
        return compressed

    def compress_observations(self, observations: Observation) -> list[Any]:
        conversion_observations = {}
        for product, observation in observations.conversionObservations.items():
            conversion_observations[product] = [
                observation.bidPrice,
                observation.askPrice,
                observation.transportFees,
                observation.exportTariff,
                observation.importTariff,
                observation.sugarPrice,
                observation.sunlightIndex,
            ]

        return [observations.plainValueObservations, conversion_observations]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
        compressed = []
        for arr in orders.values():
            for order in arr:
                compressed.append([order.symbol, order.price, order.quantity])
        return compressed

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        lo, hi = 0, min(len(value), max_length)
        out = ""

        while lo <= hi:
            mid = (lo + hi) // 2

            candidate = value[:mid]
            if len(candidate) < len(value):
                candidate += "..."

            encoded_candidate = json.dumps(candidate)

            if len(encoded_candidate) <= max_length:
                out = candidate
                lo = mid + 1
            else:
                hi = mid - 1

        return out


logger = Logger()


class Trader:
    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        conversions = 0
        trader_data = ""

        for product, order_depth in state.order_depths.items():
            position = state.position.get(product, 0)

            if product == "EMERALDS":
                result[product] = self.trade_emeralds(order_depth, position)
            elif product == "TOMATOES":
                result[product] = self.trade_tomatoes(order_depth, position, state.timestamp)
            else:
                result[product] = []

        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data

    def trade_emeralds(self, order_depth: OrderDepth, position: int) -> List[Order]:
        manager = OrderManager("EMERALDS", position, POSITION_LIMITS["EMERALDS"])
        fv = EMERALDS_FAIR_VALUE
        best_bid = self.best_bid(order_depth)
        best_ask = self.best_ask(order_depth)
        mid = self.get_mid_price(order_depth)

        # First, take any visible edge against the fixed emerald fair value.
        for ask_price, ask_volume in sorted(order_depth.sell_orders.items()):
            if ask_price < fv:
                manager.buy(ask_price, min(-ask_volume, self.edge_size_em(position, buy=True)))

        for bid_price, bid_volume in sorted(order_depth.buy_orders.items(), reverse=True):
            if bid_price > fv:
                manager.sell(bid_price, min(bid_volume, self.edge_size_em(position, buy=False)))

        # Default passive stance is to step one tick inside the current spread.
        normal_bid = None if best_bid is None else best_bid + 1
        normal_ask = None if best_ask is None else best_ask - 1

        # As inventory stretches, the strategy increasingly prioritizes flattening
        # over symmetric market making.
        if position > 55:
            flatten_ask = self.emerald_flatten_ask(position, normal_ask, mid)
            quote_ask = self.clamp_price(
                flatten_ask,
                None if best_bid is None else best_bid + 1,
                None if best_ask is None else best_ask - 1,
            )
            if quote_ask is not None:
                manager.sell(quote_ask, self.flatten_size_em(position))
            if normal_bid is not None and position < 78:
                manager.buy(normal_bid, 1)
        elif position > 40:
            if normal_ask is not None:
                manager.sell(normal_ask, self.passive_size_em(position, buy=False) + 4)
            if normal_bid is not None and position < 62:
                manager.buy(normal_bid, 3)
        elif position < -55:
            flatten_bid = self.emerald_flatten_bid(position, normal_bid, mid)
            quote_bid = self.clamp_price(
                flatten_bid,
                None if best_bid is None else best_bid + 1,
                None if best_ask is None else best_ask - 1,
            )
            if quote_bid is not None:
                manager.buy(quote_bid, self.flatten_size_em(position))
            if normal_ask is not None and position > -78:
                manager.sell(normal_ask, 1)
        elif position < -40:
            if normal_bid is not None:
                manager.buy(normal_bid, self.passive_size_em(position, buy=True) + 4)
            if normal_ask is not None and position > -62:
                manager.sell(normal_ask, 3)
        else:
            if normal_bid is not None:
                manager.buy(normal_bid, self.passive_size_em(position, buy=True))
            if normal_ask is not None:
                manager.sell(normal_ask, self.passive_size_em(position, buy=False))

        return manager.orders

    def trade_tomatoes(self, order_depth: OrderDepth, position: int, timestamp: int) -> List[Order]:
        manager = OrderManager("TOMATOES", position, POSITION_LIMITS["TOMATOES"])
        fv = TOMATOES_FAIR_VALUE
        best_bid = self.best_bid(order_depth)
        best_ask = self.best_ask(order_depth)
        mid = self.get_mid_price(order_depth)

        if mid is None:
            return manager.orders

        # Near the end, large tomato positions are reduced directly from the book.
        if timestamp >= 185000 and abs(position) >= 60:
            if position < 0:
                for ask_price, ask_volume in sorted(order_depth.sell_orders.items()):
                    size = min(-ask_volume, -position, 15)
                    if size > 0:
                        manager.buy(ask_price, size)
            elif position > 0:
                for bid_price, bid_volume in sorted(order_depth.buy_orders.items(), reverse=True):
                    size = min(bid_volume, position, 15)
                    if size > 0:
                        manager.sell(bid_price, size)
            return manager.orders

        # Keep early-round aggression small until the book has had time to settle.
        warmup_size = 2 if timestamp < 10000 else 20

        for ask_price, ask_volume in sorted(order_depth.sell_orders.items()):
            if ask_price <= fv - 3:
                size = min(self.tom_aggressive_size(position, buy=True), warmup_size)
                manager.buy(ask_price, min(-ask_volume, size))

        for bid_price, bid_volume in sorted(order_depth.buy_orders.items(), reverse=True):
            if bid_price >= fv + 3:
                size = min(self.tom_aggressive_size(position, buy=False), warmup_size)
                manager.sell(bid_price, min(bid_volume, size))

        # Reservation price shifts against inventory so passive quotes lean toward flat.
        reservation = fv - 0.15 * position
        spread = 3
        bid_target = reservation - spread
        ask_target = reservation + spread

        if position >= 50:
            allow_bid = False
            allow_ask = True
            ask_target = min(ask_target, reservation + 1)
        elif position <= -50:
            allow_bid = True
            allow_ask = False
            bid_target = max(bid_target, reservation - 1)
        elif position >= 25:
            allow_bid = True
            allow_ask = True
            bid_target -= 1
        elif position <= -25:
            allow_bid = True
            allow_ask = True
            ask_target += 1
        else:
            allow_bid = True
            allow_ask = True

        quote_bid = self.clamp_price(
            round(bid_target),
            None if best_bid is None else best_bid + 1,
            None if best_ask is None else best_ask - 1,
        )
        quote_ask = self.clamp_price(
            round(ask_target),
            None if best_bid is None else best_bid + 1,
            None if best_ask is None else best_ask - 1,
        )

        bid_size = self.tom_passive_size(position, buy=True)
        ask_size = self.tom_passive_size(position, buy=False)

        if quote_bid is not None and allow_bid:
            manager.buy(quote_bid, bid_size)
        if quote_ask is not None and allow_ask:
            manager.sell(quote_ask, ask_size)

        # Keep the winning baseline intact and only add a very late, gentle trim.
        if timestamp >= TOMATOES_LATE_GENTLE_TIMESTAMP and position >= TOMATOES_LATE_GENTLE_POSITION:
            for bid_price, bid_volume in sorted(order_depth.buy_orders.items(), reverse=True):
                size = min(bid_volume, position, TOMATOES_LATE_GENTLE_SIZE)
                if size > 0:
                    manager.sell(bid_price, size)
                    break
        elif timestamp >= TOMATOES_LATE_GENTLE_TIMESTAMP and position <= -TOMATOES_LATE_GENTLE_POSITION:
            for ask_price, ask_volume in sorted(order_depth.sell_orders.items()):
                size = min(-ask_volume, -position, TOMATOES_LATE_GENTLE_SIZE)
                if size > 0:
                    manager.buy(ask_price, size)
                    break

        return manager.orders

    def tom_aggressive_size(self, position: int, buy: bool) -> int:
        # Larger tomato taker clips are allowed near flat; size is reduced as
        # inventory grows, with a small bonus when trading back toward neutral.
        abs_pos = abs(position)
        base = 20
        if abs_pos >= 70:
            base = 3
        elif abs_pos >= 55:
            base = 8
        elif abs_pos >= 35:
            base = 14
        if buy and position < 0:
            base += 4
        if (not buy) and position > 0:
            base += 4
        return max(2, min(25, base))

    def tom_passive_size(self, position: int, buy: bool) -> int:
        # Passive tomato size is much smaller than taker size and tapers faster.
        abs_pos = abs(position)
        size = 5
        if abs_pos >= 70:
            size = 1
        elif abs_pos >= 55:
            size = 2
        elif abs_pos >= 35:
            size = 3
        if buy and position < -20:
            size += 1
        if (not buy) and position > 20:
            size += 1
        return max(1, min(8, size))

    def edge_size_em(self, position: int, buy: bool) -> int:
        # Emeralds can trade in larger clips, but aggression still scales down
        # near the hard position limits.
        abs_pos = abs(position)
        base = 24
        if abs_pos >= 70:
            base = 8
        elif abs_pos >= 55:
            base = 12
        elif abs_pos >= 35:
            base = 18
        if buy and position < 0:
            base += 4
        if (not buy) and position > 0:
            base += 4
        return max(2, min(28, base))

    def passive_size_em(self, position: int, buy: bool) -> int:
        # Passive emerald size stays large near flat, then shrinks as inventory grows.
        abs_pos = abs(position)
        size = 20
        if abs_pos >= 70:
            size = 4
        elif abs_pos >= 55:
            size = 8
        elif abs_pos >= 35:
            size = 12
        if buy and position < -25:
            size += 2
        if (not buy) and position > 25:
            size += 2
        return max(1, min(24, size))

    def flatten_size_em(self, position: int) -> int:
        # Once emerald inventory is stretched, flatten using larger clips.
        abs_pos = abs(position)
        if abs_pos >= 75:
            return 20
        if abs_pos >= 65:
            return 16
        return 12

    def emerald_flatten_ask(self, position, normal_ask, mid):
        if normal_ask is None:
            return int(mid) if mid is not None else None
        if position >= 75:
            return max(10003, normal_ask - 4)
        if position >= 70:
            return max(10005, normal_ask - 2)
        return normal_ask

    def emerald_flatten_bid(self, position, normal_bid, mid):
        if normal_bid is None:
            return int(mid) if mid is not None else None
        if position <= -75:
            return min(9997, normal_bid + 4)
        if position <= -70:
            return min(9995, normal_bid + 2)
        return normal_bid

    def best_bid(self, order_depth: OrderDepth):
        if not order_depth.buy_orders:
            return None
        return max(order_depth.buy_orders)

    def best_ask(self, order_depth: OrderDepth):
        if not order_depth.sell_orders:
            return None
        return min(order_depth.sell_orders)

    def get_mid_price(self, order_depth: OrderDepth):
        bb = self.best_bid(order_depth)
        ba = self.best_ask(order_depth)
        if bb is None or ba is None:
            return None
        return (bb + ba) / 2

    def clamp_price(self, desired, lower_bound, upper_bound):
        if desired is None:
            return None
        desired = int(desired)
        if lower_bound is not None and desired < lower_bound:
            desired = int(lower_bound)
        if upper_bound is not None and desired > upper_bound:
            desired = int(upper_bound)
        if lower_bound is not None and upper_bound is not None and lower_bound > upper_bound:
            return None
        return desired


class OrderManager:
    def __init__(self, product: str, position: int, limit: int):
        # Remaining room is tracked separately on each side so strategy code can
        # place multiple orders without recalculating position-limit headroom.
        self.product = product
        self.orders: List[Order] = []
        self.buy_remaining = max(0, limit - position)
        self.sell_remaining = max(0, limit + position)

    def buy(self, price: int, quantity: int) -> None:
        size = min(max(0, int(quantity)), self.buy_remaining)
        if size <= 0:
            return
        self.orders.append(Order(self.product, int(price), size))
        self.buy_remaining -= size

    def sell(self, price: int, quantity: int) -> None:
        size = min(max(0, int(quantity)), self.sell_remaining)
        if size <= 0:
            return
        self.orders.append(Order(self.product, int(price), -size))
        self.sell_remaining -= size
