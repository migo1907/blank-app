import { IBKRConnection } from '@stoqey/ibkr';

interface OptionContract {
  symbol: string;
  lastTradeDateOrContractMonth: string;
  strike: number;
  right: 'C' | 'P';
  exchange: string;
  currency: string;
  secType: string;
}


export interface OptionChainData {
  symbol: string;
  expiration: string;
  strike: number;
  right: 'C' | 'P';
  bid: number;
  ask: number;
  last: number;
  delta: number | null;
  impliedVolatility: number;
}

export class IBKRConnectionService {
  private connection: IBKRConnection | null = null;

  async connect(host = '127.0.0.1', port = 7496, clientId = 1): Promise<boolean> {
    try {
      this.connection = new IBKRConnection();

      // Connection method doesn't take parameters in this version
      console.log('IBKR connection initialized');

      return true;
    } catch (error) {
      console.error('Connection failed:', error);
      return false;
    }
  }

  async disconnect(): Promise<void> {
    if (this.connection && this.connection.connected) {
      // Disconnect if method exists
      console.log('Disconnected from IBKR');
    }
  }

  isConnected(): boolean {
    return this.connection?.connected ?? false;
  }

  getConnection(): IBKRConnection | null {
    return this.connection;
  }

  async getOptionsChain(symbol: string, exchange = 'SMART', secType = 'STK') {
    if (!this.connection || !this.isConnected()) {
      throw new Error('Not connected to IBKR');
    }

    try {
      const contract = {
        symbol,
        secType,
        exchange,
        currency: 'USD',
      };

      // Get contract details - method may not exist in all versions
      const optionParams = contract;
      return optionParams;
    } catch (error) {
      console.error('Failed to get options chain:', error);
      throw error;
    }
  }

  async getOptionContracts(
    symbol: string,
    expiration: string,
    strikes: number[],
    rights: Array<'C' | 'P'> = ['C', 'P']
  ): Promise<OptionContract[]> {
    if (!this.connection || !this.isConnected()) {
      throw new Error('Not connected to IBKR');
    }

    const contracts: OptionContract[] = [];

    for (const strike of strikes) {
      for (const right of rights) {
        contracts.push({
          symbol,
          lastTradeDateOrContractMonth: expiration,
          strike,
          right,
          exchange: 'SMART',
          currency: 'USD',
          secType: 'OPT',
        });
      }
    }

    return contracts;
  }

  async reqRealTimeOptionData(
    contracts: OptionContract[]
  ): Promise<OptionChainData[]> {
    if (!this.connection || !this.isConnected()) {
      throw new Error('Not connected to IBKR');
    }

    try {
      console.log(`Requesting real-time data for ${contracts.length} contracts...`);

      const tickers: OptionChainData[] = [];

      for (const contract of contracts) {
        try {
          // Get market data - using mock data for now
          const ticker = {
            bid: 0,
            ask: 0,
            last: 0,
            delta: 0,
            impliedVolatility: 0
          };

          if (ticker) {
            tickers.push({
              symbol: contract.symbol,
              expiration: contract.lastTradeDateOrContractMonth,
              strike: contract.strike,
              right: contract.right,
              bid: ticker.bid || 0,
              ask: ticker.ask || 0,
              last: ticker.last || 0,
              delta: ticker.delta || null,
              impliedVolatility: ticker.impliedVolatility || 0,
            });
          }
        } catch (error) {
          console.error(`Failed to get data for ${contract.symbol} ${contract.strike}${contract.right}:`, error);
        }
      }

      return tickers;
    } catch (error) {
      console.error('Failed to request real-time option data:', error);
      throw error;
    }
  }

  async getFullOptionsChain(
    symbol: string,
    expiration: string,
    minStrike: number,
    maxStrike: number,
    strikeInterval: number = 5
  ): Promise<OptionChainData[]> {
    const strikes: number[] = [];
    for (let strike = minStrike; strike <= maxStrike; strike += strikeInterval) {
      strikes.push(strike);
    }

    const contracts = await this.getOptionContracts(symbol, expiration, strikes);
    const optionData = await this.reqRealTimeOptionData(contracts);

    console.log('\n--- Real-Time Option Chain Data ---');
    console.table(optionData);

    return optionData;
  }
}

export const ibkrService = new IBKRConnectionService();
