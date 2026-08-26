package types

import (
	"time"

	"github.com/shopspring/decimal"
)

type Symbol string

type OrderSide int

const (
	Buy OrderSide = iota
	Sell
)

func (s OrderSide) String() string {
	switch s {
	case Buy:
		return "buy"
	case Sell:
		return "sell"
	default:
		return "unknown"
	}
}

type OrderType int

const (
	Limit OrderType = iota
	Market
	StopLimit
	StopMarket
	TrailingStop
	Iceberg
)

func (t OrderType) String() string {
	switch t {
	case Limit:
		return "limit"
	case Market:
		return "market"
	case StopLimit:
		return "stop_limit"
	case StopMarket:
		return "stop_market"
	case TrailingStop:
		return "trailing_stop"
	case Iceberg:
		return "iceberg"
	default:
		return "unknown"
	}
}

type TimeInForce int

const (
	GTC TimeInForce = iota
	IOC
	FOK
	GTD
)

type OrderStatus int

const (
	New OrderStatus = iota
	PartiallyFilled
	Filled
	Cancelled
	Rejected
	Expired
)

type Order struct {
	ID            string          `json:"id"`
	ClientOrderID string          `json:"client_order_id"`
	Symbol        Symbol          `json:"symbol"`
	Side          OrderSide       `json:"side"`
	Type          OrderType       `json:"type"`
	Status        OrderStatus     `json:"status"`
	Price         decimal.Decimal `json:"price"`
	StopPrice     decimal.Decimal `json:"stop_price,omitempty"`
	Quantity      decimal.Decimal `json:"quantity"`
	FilledQty     decimal.Decimal `json:"filled_quantity"`
	RemainingQty  decimal.Decimal `json:"remaining_quantity"`
	LeavesQty     decimal.Decimal `json:"leaves_quantity"`
	CumQuoteQty   decimal.Decimal `json:"cumulative_quote_quantity"`
	AvgPrice      decimal.Decimal `json:"avg_price"`
	TimeInForce   TimeInForce     `json:"time_in_force"`
	CreatedAt     time.Time       `json:"created_at"`
	UpdatedAt     time.Time       `json:"updated_at"`
	ExpireAt      *time.Time      `json:"expire_at,omitempty"`
	IcebergQty    decimal.Decimal `json:"iceberg_quantity,omitempty"`
	DisplayQty    decimal.Decimal `json:"display_quantity,omitempty"`
}

type Trade struct {
	ID          string          `json:"id"`
	Symbol      Symbol          `json:"symbol"`
	BuyOrderID  string          `json:"buy_order_id"`
	SellOrderID string          `json:"sell_order_id"`
	Price       decimal.Decimal `json:"price"`
	Quantity    decimal.Decimal `json:"quantity"`
	QuoteQty    decimal.Decimal `json:"quote_quantity"`
	TakerSide   OrderSide       `json:"taker_side"`
	Timestamp   time.Time       `json:"timestamp"`
	IsBuyerMaker bool           `json:"is_buyer_maker"`
}

type Ticker struct {
	Symbol      Symbol          `json:"symbol"`
	BidPrice    decimal.Decimal `json:"bid_price"`
	AskPrice    decimal.Decimal `json:"ask_price"`
	LastPrice   decimal.Decimal `json:"last_price"`
	Volume24h   decimal.Decimal `json:"volume_24h"`
	QuoteVolume decimal.Decimal `json:"quote_volume"`
	High24h     decimal.Decimal `json:"high_24h"`
	Low24h      decimal.Decimal `json:"low_24h"`
	Open24h     decimal.Decimal `json:"open_24h"`
	Change24h   decimal.Decimal `json:"change_24h"`
	ChangePct   decimal.Decimal `json:"change_percent"`
	Count       int64           `json:"trade_count"`
	UpdatedAt   time.Time       `json:"updated_at"`
}

type Candle struct {
	Symbol    Symbol          `json:"symbol"`
	Interval  string          `json:"interval"`
	OpenTime  time.Time       `json:"open_time"`
	CloseTime time.Time       `json:"close_time"`
	Open      decimal.Decimal `json:"open"`
	High      decimal.Decimal `json:"high"`
	Low       decimal.Decimal `json:"low"`
	Close     decimal.Decimal `json:"close"`
	Volume    decimal.Decimal `json:"volume"`
	QuoteVol  decimal.Decimal `json:"quote_volume"`
	Trades    int64           `json:"trades"`
}

type Level struct {
	Price    decimal.Decimal `json:"price"`
	Quantity decimal.Decimal `json:"quantity"`
	Count    int64           `json:"order_count"`
}

type DepthUpdate struct {
	Symbol    Symbol  `json:"symbol"`
	Bids      []Level `json:"bids"`
	Asks      []Level `json:"asks"`
	Timestamp int64   `json:"timestamp"`
}

type MarketEvent struct {
	Type    string      `json:"type"`
	Symbol  Symbol      `json:"symbol"`
	Payload interface{} `json:"payload,omitempty"`
}
