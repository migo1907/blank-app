import { ibkrService } from '../src/services/ibkrConnectionService';

async function testIBKRConnection() {
  try {
    const connected = await ibkrService.connect('127.0.0.1', 7496, 1);

    if (connected) {
      console.log('Successfully connected to IBKR!');

      const symbol = 'AAPL';
      const expiration = '20250117';
      const minStrike = 170;
      const maxStrike = 190;
      const strikeInterval = 5;

      console.log(`\nFetching options chain for ${symbol}...`);
      console.log(`Expiration: ${expiration}`);
      console.log(`Strike range: $${minStrike} - $${maxStrike} (interval: $${strikeInterval})`);

      const optionChainData = await ibkrService.getFullOptionsChain(
        symbol,
        expiration,
        minStrike,
        maxStrike,
        strikeInterval
      );

      console.log(`\nReceived ${optionChainData.length} option contracts`);
      console.log('\n--- Filtered Real-Time Option Chain ---');
      console.table(optionChainData.map(opt => ({
        Symbol: opt.symbol,
        Expiration: opt.expiration,
        Strike: `$${opt.strike}`,
        Type: opt.right === 'C' ? 'Call' : 'Put',
        Bid: opt.bid.toFixed(2),
        Ask: opt.ask.toFixed(2),
        Last: opt.last.toFixed(2),
        Delta: opt.delta?.toFixed(4) || 'N/A',
        IV: `${(opt.impliedVolatility * 100).toFixed(2)}%`
      })));
    }
  } catch (error) {
    console.error('Connection failed:', error);
  } finally {
    if (ibkrService.isConnected()) {
      await ibkrService.disconnect();
      console.log('\nDisconnected from IBKR');
    }
  }
}

testIBKRConnection();
