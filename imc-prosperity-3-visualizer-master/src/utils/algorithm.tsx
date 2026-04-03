import { Text } from '@mantine/core';
import { ReactNode } from 'react';
import {
  ActivityLogRow,
  Algorithm,
  AlgorithmDataRow,
  AlgorithmSummary,
  CompressedAlgorithmDataRow,
  CompressedListing,
  CompressedObservations,
  CompressedOrder,
  CompressedOrderDepth,
  CompressedTrade,
  CompressedTradingState,
  ConversionObservation,
  Listing,
  Observation,
  Order,
  OrderDepth,
  Product,
  ProsperitySymbol,
  Trade,
  TradingState,
} from '../models.ts';
import { authenticatedAxios } from './axios.ts';

export class AlgorithmParseError extends Error {
  public constructor(public readonly node: ReactNode) {
    super('Failed to parse algorithm logs');
  }
}

interface ImcResultTrade {
  symbol: string;
  timestamp: number | string;
  price: number | string;
  quantity: number | string;
  buyer?: string;
  seller?: string;
}

interface ImcResultJson {
  activitiesLog: string;
  tradeHistory?: ImcResultTrade[];
}

function getColumnValues(columns: string[], indices: number[]): number[] {
  const values: number[] = [];

  for (const index of indices) {
    const value = columns[index];
    if (value !== '') {
      values.push(parseFloat(value));
    }
  }

  return values;
}

function getActivityLogs(logLines: string[]): ActivityLogRow[] {
  const headerIndex = logLines.indexOf('Activities log:');
  if (headerIndex === -1) {
    return [];
  }

  const rows: ActivityLogRow[] = [];

  for (let i = headerIndex + 2; i < logLines.length; i++) {
    const line = logLines[i];
    if (line === '') {
      break;
    }

    const columns = line.split(';');

    rows.push({
      day: Number(columns[0]),
      timestamp: Number(columns[1]),
      product: columns[2],
      bidPrices: getColumnValues(columns, [3, 5, 7]),
      bidVolumes: getColumnValues(columns, [4, 6, 8]),
      askPrices: getColumnValues(columns, [9, 11, 13]),
      askVolumes: getColumnValues(columns, [10, 12, 14]),
      midPrice: Number(columns[15]),
      profitLoss: Number(columns[16]),
    });
  }

  return rows;
}

function getActivityRowsFromActivitiesLog(activitiesLog: string): ActivityLogRow[] {
  const lines = activitiesLog
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(line => line.length > 0);

  if (lines.length <= 1) {
    return [];
  }

  const rows: ActivityLogRow[] = [];

  for (let i = 1; i < lines.length; i++) {
    const columns = lines[i].split(';');

    rows.push({
      day: Number(columns[0]),
      timestamp: Number(columns[1]),
      product: columns[2],
      bidPrices: getColumnValues(columns, [3, 5, 7]),
      bidVolumes: getColumnValues(columns, [4, 6, 8]),
      askPrices: getColumnValues(columns, [9, 11, 13]),
      askVolumes: getColumnValues(columns, [10, 12, 14]),
      midPrice: Number(columns[15]),
      profitLoss: Number(columns[16]),
    });
  }

  return rows;
}

function decompressListings(compressed: CompressedListing[]): Record<ProsperitySymbol, Listing> {
  const listings: Record<ProsperitySymbol, Listing> = {};

  for (const [symbol, product, denomination] of compressed) {
    listings[symbol] = {
      symbol,
      product,
      denomination,
    };
  }

  return listings;
}

function decompressOrderDepths(
  compressed: Record<ProsperitySymbol, CompressedOrderDepth>,
): Record<ProsperitySymbol, OrderDepth> {
  const orderDepths: Record<ProsperitySymbol, OrderDepth> = {};

  for (const [symbol, [buyOrders, sellOrders]] of Object.entries(compressed)) {
    orderDepths[symbol] = {
      buyOrders,
      sellOrders,
    };
  }

  return orderDepths;
}

function decompressTrades(compressed: CompressedTrade[]): Record<ProsperitySymbol, Trade[]> {
  const trades: Record<ProsperitySymbol, Trade[]> = {};

  for (const [symbol, price, quantity, buyer, seller, timestamp] of compressed) {
    if (trades[symbol] === undefined) {
      trades[symbol] = [];
    }

    trades[symbol].push({
      symbol,
      price,
      quantity,
      buyer,
      seller,
      timestamp,
    });
  }

  return trades;
}

function decompressObservations(compressed: CompressedObservations): Observation {
  const conversionObservations: Record<Product, ConversionObservation> = {};

  for (const [
    product,
    [bidPrice, askPrice, transportFees, exportTariff, importTariff, sugarPrice, sunlightIndex],
  ] of Object.entries(compressed[1])) {
    conversionObservations[product] = {
      bidPrice,
      askPrice,
      transportFees,
      exportTariff,
      importTariff,
      sugarPrice,
      sunlightIndex,
    };
  }

  return {
    plainValueObservations: compressed[0],
    conversionObservations,
  };
}

function decompressState(compressed: CompressedTradingState): TradingState {
  return {
    timestamp: compressed[0],
    traderData: compressed[1],
    listings: decompressListings(compressed[2]),
    orderDepths: decompressOrderDepths(compressed[3]),
    ownTrades: decompressTrades(compressed[4]),
    marketTrades: decompressTrades(compressed[5]),
    position: compressed[6],
    observations: decompressObservations(compressed[7]),
  };
}

function decompressOrders(compressed: CompressedOrder[]): Record<ProsperitySymbol, Order[]> {
  const orders: Record<ProsperitySymbol, Order[]> = {};

  for (const [symbol, price, quantity] of compressed) {
    if (orders[symbol] === undefined) {
      orders[symbol] = [];
    }

    orders[symbol].push({
      symbol,
      price,
      quantity,
    });
  }

  return orders;
}

function decompressDataRow(compressed: CompressedAlgorithmDataRow, sandboxLogs: string): AlgorithmDataRow {
  return {
    state: decompressState(compressed[0]),
    orders: decompressOrders(compressed[1]),
    conversions: compressed[2],
    traderData: compressed[3],
    algorithmLogs: compressed[4],
    sandboxLogs,
  };
}

function toOrderMap(prices: number[], volumes: number[], isSell: boolean): Record<number, number> {
  const orders: Record<number, number> = {};

  for (let i = 0; i < Math.min(prices.length, volumes.length); i++) {
    const price = prices[i]!;
    const volume = volumes[i]!;
    orders[price] = isSell ? -Math.abs(volume) : Math.abs(volume);
  }

  return orders;
}

function getAlgorithmDataFromImcResult(activityLogs: ActivityLogRow[], tradeHistory: ImcResultTrade[]): AlgorithmDataRow[] {
  const booksByTimestamp: Record<number, Record<string, ActivityLogRow>> = {};
  const products = new Set<string>();

  for (const row of activityLogs) {
    if (booksByTimestamp[row.timestamp] === undefined) {
      booksByTimestamp[row.timestamp] = {};
    }

    booksByTimestamp[row.timestamp]![row.product] = row;
    products.add(row.product);
  }

  const sortedProducts = [...products].sort();
  const timestamps = Object.keys(booksByTimestamp)
    .map(Number)
    .sort((a, b) => a - b);

  const ownTradesByTimestamp: Record<number, Record<string, CompressedTrade[]>> = {};

  for (const trade of [...tradeHistory].sort((a, b) => Number(a.timestamp) - Number(b.timestamp))) {
    const buyer = trade.buyer ?? '';
    const seller = trade.seller ?? '';
    if (buyer !== 'SUBMISSION' && seller !== 'SUBMISSION') {
      continue;
    }

    const timestamp = Number(trade.timestamp);
    const symbol = trade.symbol;
    if (ownTradesByTimestamp[timestamp] === undefined) {
      ownTradesByTimestamp[timestamp] = {};
    }
    if (ownTradesByTimestamp[timestamp]![symbol] === undefined) {
      ownTradesByTimestamp[timestamp]![symbol] = [];
    }

    ownTradesByTimestamp[timestamp]![symbol]!.push([
      symbol,
      Number(trade.price),
      Number(trade.quantity),
      buyer,
      seller,
      timestamp,
    ]);
  }

  const positionBySymbol: Record<string, number> = {};
  const positionSnapshots: Record<number, Record<string, number>> = {};

  for (const timestamp of timestamps) {
    for (const [symbol, trades] of Object.entries(ownTradesByTimestamp[timestamp] ?? {})) {
      for (const trade of trades) {
        if (trade[3] === 'SUBMISSION') {
          positionBySymbol[symbol] = (positionBySymbol[symbol] ?? 0) + trade[2];
        } else if (trade[4] === 'SUBMISSION') {
          positionBySymbol[symbol] = (positionBySymbol[symbol] ?? 0) - trade[2];
        }
      }
    }

    positionSnapshots[timestamp] = { ...positionBySymbol };
  }

  const listings: CompressedListing[] = sortedProducts.map(product => [product, product, 'XIRECS']);
  const observations: CompressedObservations = [{}, {}];

  const data: AlgorithmDataRow[] = [];
  for (const timestamp of timestamps) {
    const orderDepths: Record<ProsperitySymbol, CompressedOrderDepth> = {};

    for (const product of sortedProducts) {
      const row = booksByTimestamp[timestamp]![product];
      if (row === undefined) {
        continue;
      }

      orderDepths[product] = [
        toOrderMap(row.bidPrices, row.bidVolumes, false),
        toOrderMap(row.askPrices, row.askVolumes, true),
      ];
    }

    const ownTrades: CompressedTrade[] = [];
    for (const product of sortedProducts) {
      ownTrades.push(...(ownTradesByTimestamp[timestamp]?.[product] ?? []));
    }

    const compressedRow: CompressedAlgorithmDataRow = [
      [
        timestamp,
        '',
        listings,
        orderDepths,
        ownTrades,
        [],
        positionSnapshots[timestamp] ?? {},
        observations,
      ],
      [],
      0,
      '',
      '',
    ];

    data.push(decompressDataRow(compressedRow, ''));
  }

  return data;
}

function parseAlgorithmFromImcResultJson(logs: string, summary?: AlgorithmSummary): Algorithm | undefined {
  try {
    let parsed: unknown;
    try {
      parsed = JSON.parse(logs);
    } catch {
      return undefined;
    }

    if (typeof parsed !== 'object' || parsed === null || !('activitiesLog' in parsed)) {
      return undefined;
    }

    const result = parsed as ImcResultJson;
    if (typeof result.activitiesLog !== 'string') {
      return undefined;
    }

    const tradeHistory = Array.isArray(result.tradeHistory) ? result.tradeHistory : [];
    const activityLogs = getActivityRowsFromActivitiesLog(result.activitiesLog);
    const data = getAlgorithmDataFromImcResult(activityLogs, tradeHistory);

    if (activityLogs.length === 0 || data.length === 0) {
      return undefined;
    }

    return {
      summary,
      activityLogs,
      data,
    };
  } catch {
    return undefined;
  }
}

function getAlgorithmData(logLines: string[]): AlgorithmDataRow[] {
  const headerIndex = logLines.indexOf('Sandbox logs:');
  if (headerIndex === -1) {
    return [];
  }

  const rows: AlgorithmDataRow[] = [];
  let nextSandboxLogs = '';

  const sandboxLogPrefix = '  "sandboxLog": ';
  const lambdaLogPrefix = '  "lambdaLog": ';

  for (let i = headerIndex + 1; i < logLines.length; i++) {
    const line = logLines[i];
    if (line.endsWith(':')) {
      break;
    }

    if (line.startsWith(sandboxLogPrefix)) {
      nextSandboxLogs = JSON.parse(line.substring(sandboxLogPrefix.length, line.length - 1)).trim();

      if (nextSandboxLogs.startsWith('Conversion request')) {
        const lastRow = rows[rows.length - 1];
        lastRow.sandboxLogs += (lastRow.sandboxLogs.length > 0 ? '\n' : '') + nextSandboxLogs;

        nextSandboxLogs = '';
      }

      continue;
    }

    if (!line.startsWith(lambdaLogPrefix) || line === '  "lambdaLog": "",') {
      continue;
    }

    const start = line.indexOf('[[');
    const end = line.lastIndexOf(']') + 1;

    try {
      const compressedDataRow = JSON.parse(JSON.parse('"' + line.substring(start, end) + '"'));
      rows.push(decompressDataRow(compressedDataRow, nextSandboxLogs));
    } catch (err) {
      console.log(line);
      console.error(err);

      throw new AlgorithmParseError(
        (
          <>
            <Text>Logs are in invalid format. Could not parse the following line:</Text>
            <Text>{line}</Text>
          </>
        ),
      );
    }
  }

  return rows;
}

export function parseAlgorithmLogs(logs: string, summary?: AlgorithmSummary): Algorithm {
  const parsedImcResult = parseAlgorithmFromImcResultJson(logs, summary);
  if (parsedImcResult !== undefined) {
    return parsedImcResult;
  }

  const logLines = logs.trim().split(/\r?\n/);

  const activityLogs = getActivityLogs(logLines);
  const data = getAlgorithmData(logLines);

  if (activityLogs.length === 0 && data.length === 0) {
    throw new AlgorithmParseError(
      (
        <Text>
          Logs are empty, either something went wrong with your submission or your backtester logs in a different format
          than Prosperity&apos;s submission environment.
        </Text>
      ),
    );
  }

  if (activityLogs.length === 0 || data.length === 0) {
    throw new AlgorithmParseError(
      /* prettier-ignore */
      <Text>Logs are in invalid format.</Text>,
    );
  }

  return {
    summary,
    activityLogs,
    data,
  };
}

export async function getAlgorithmLogsUrl(algorithmId: string): Promise<string> {
  const urlResponse = await authenticatedAxios.get(
    `https://bz97lt8b1e.execute-api.eu-west-1.amazonaws.com/prod/submission/logs/${algorithmId}`,
  );

  return urlResponse.data;
}

function downloadFile(url: string): void {
  const link = document.createElement('a');
  link.href = url;
  link.download = new URL(url).pathname.split('/').pop()!;
  link.target = '_blank';
  link.rel = 'noreferrer';

  document.body.appendChild(link);
  link.click();
  link.remove();
}

export async function downloadAlgorithmLogs(algorithmId: string): Promise<void> {
  const logsUrl = await getAlgorithmLogsUrl(algorithmId);
  downloadFile(logsUrl);
}

export async function downloadAlgorithmResults(algorithmId: string): Promise<void> {
  const detailsResponse = await authenticatedAxios.get(
    `https://bz97lt8b1e.execute-api.eu-west-1.amazonaws.com/prod/results/tutorial/${algorithmId}`,
  );

  downloadFile(detailsResponse.data.algo.summary.activitiesLog);
}
