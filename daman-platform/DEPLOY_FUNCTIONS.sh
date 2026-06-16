#!/bin/bash

# Deploy All Edge Functions with Alpaca as Primary
# This script deploys the 3 updated edge functions to Supabase

echo "🚀 Deploying Edge Functions with Alpaca Primary..."
echo ""

# Check if supabase CLI is installed
if ! command -v supabase &> /dev/null; then
    echo "❌ Supabase CLI not found!"
    echo "Install with: npm install -g supabase"
    exit 1
fi

# Check if logged in
echo "Checking Supabase authentication..."
supabase projects list > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "❌ Not logged in to Supabase!"
    echo "Login with: supabase login"
    exit 1
fi

echo "✅ Supabase CLI ready"
echo ""

# Deploy fetch-stock-data
echo "📦 Deploying fetch-stock-data (Alpaca primary for stock quotes)..."
supabase functions deploy fetch-stock-data
if [ $? -eq 0 ]; then
    echo "✅ fetch-stock-data deployed successfully"
else
    echo "❌ fetch-stock-data deployment failed"
    exit 1
fi
echo ""

# Deploy fetch-options-prices
echo "📦 Deploying fetch-options-prices (Alpaca primary for options)..."
supabase functions deploy fetch-options-prices
if [ $? -eq 0 ]; then
    echo "✅ fetch-options-prices deployed successfully"
else
    echo "❌ fetch-options-prices deployment failed"
    exit 1
fi
echo ""

# Deploy fetch-intraday-data
echo "📦 Deploying fetch-intraday-data (Alpaca primary for bars)..."
supabase functions deploy fetch-intraday-data
if [ $? -eq 0 ]; then
    echo "✅ fetch-intraday-data deployed successfully"
else
    echo "❌ fetch-intraday-data deployment failed"
    exit 1
fi
echo ""

echo "🎉 All edge functions deployed successfully!"
echo ""
echo "📋 Summary:"
echo "  - fetch-stock-data: Alpaca → Yahoo → Tradier"
echo "  - fetch-options-prices: Alpaca → Yahoo → Tradier"
echo "  - fetch-intraday-data: Alpaca → Tradier"
echo ""
echo "🧪 Test your scanners now:"
echo "  1. Open your app in browser"
echo "  2. Click QuantFlow Scanner - verify prices update"
echo "  3. Click SPX Options Scanner - verify options load"
echo "  4. Check browser console for 'source: alpaca'"
echo ""
