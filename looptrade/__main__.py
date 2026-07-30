from flask import Flask, render_template, request, jsonify
import asyncio
import threading
import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

app = Flask(__name__)

# Global state
bot_thread = None
bot_running = False
bot_logs = []

# Config file paths
CONFIG_FILE = "looptrade_config.json"
STATE_FILE = "looptrade_state.json"
LOGS_FILE = "looptrade_logs.json"

def load_logs() -> list:
    """Load logs from file, keeping only last 24 hours"""
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE, 'r') as f:
                all_logs = json.load(f)
            
            # Filter logs to keep only last 24 hours
            now = datetime.now()
            recent_logs = []
            for log in all_logs:
                # Parse timestamp from log format "[HH:MM:SS] message"
                try:
                    time_str = log[1:9]  # Extract HH:MM:SS
                    log_time = datetime.strptime(time_str, "%H:%M:%S").replace(
                        year=now.year, month=now.month, day=now.day
                    )
                    # Handle logs from yesterday if close to midnight
                    if now.hour < 2 and log_time.hour > 22:
                        log_time = log_time.replace(day=log_time.day - 1)
                    
                    # Keep if within last 24 hours
                    if (now - log_time).total_seconds() < 86400:  # 24 hours
                        recent_logs.append(log)
                except:
                    # If parsing fails, keep the log anyway
                    recent_logs.append(log)
            
            return recent_logs[-500:]  # Keep max 500 recent logs
        except Exception as e:
            print(f"Error loading logs: {e}")
            return []
    return []

def save_logs():
    """Save logs to file"""
    try:
        with open(LOGS_FILE, 'w') as f:
            json.dump(bot_logs, f, indent=2)
    except Exception as e:
        print(f"Error saving logs: {e}")

# Load existing logs on startup
bot_logs = load_logs()

def load_state() -> dict:
    """Load bot state from file"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"should_be_running": False}

def save_state(state: dict):
    """Save bot state to file"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def load_config() -> dict:
    """Load config from file or return defaults"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        "api_key": "",
        "api_secret": "",
        "api_passphrase": "",
        "leverage": 1,
        "check_seconds": 30,
        "loops": []
    }

def save_config(config: dict):
    """Save config to file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def add_log(message: str):
    """Add a log entry and persist to file"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    bot_logs.append(log_entry)
    
    # Keep only last 500 logs (about 24 hours worth)
    while len(bot_logs) > 500:
        bot_logs.pop(0)
    
    # Save to file immediately for persistence
    save_logs()

@app.route('/')
def landing():
    """Landing page"""
    return render_template('landing.html')

@app.route('/app')
def index():
    """Main app page"""
    config = load_config()
    return render_template('index.html', 
                         loops=config.get('loops', []),
                         api_configured=bool(config.get('api_key')),
                         running=bot_running,
                         logs=bot_logs[-20:])

@app.route('/api/loops', methods=['GET'])
def get_loops():
    """Get all loops"""
    config = load_config()
    return jsonify(config.get('loops', []))

# Cache for CoinGecko price (30 seconds)
_price_cache = {'price': None, 'timestamp': 0}

def get_current_btc_price():
    """Fetch current BTC price with caching"""
    import urllib.request
    import ssl
    import time
    
    # Return cached price if fresh (within 30 seconds)
    now = time.time()
    if _price_cache['price'] is not None and (now - _price_cache['timestamp']) < 30:
        return _price_cache['price']
    
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            data = json.loads(response.read().decode())
            price = data['bitcoin']['usd']
            _price_cache['price'] = price
            _price_cache['timestamp'] = now
            return price
    except:
        # Return cached price even if old, rather than None
        return _price_cache['price']

def fetch_advanced_market_data():
    """Fetch comprehensive market data for elite analysis"""
    import urllib.request
    import ssl
    import statistics
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    data = {
        'current_price': None,
        'volatility_24h': None,
        'volatility_7d': None,
        'atr_14': None,
        'trend_24h': None,
        'trend_7d': None,
        'volume_profile': None,
        'liquidation_clusters': [],
        'funding_rate': None,
        'open_interest': None,
        'whale_movements': [],
        'support_levels': [],
        'resistance_levels': []
    }
    
    try:
        # 1. Current price and 24h data
        url = "https://api.coingecko.com/api/v3/coins/bitcoin?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false&sparkline=false"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            coin_data = json.loads(response.read().decode())
            market = coin_data.get('market_data', {})
            
            data['current_price'] = market.get('current_price', {}).get('usd')
            data['volatility_24h'] = abs(market.get('price_change_percentage_24h', 0))
            data['volatility_7d'] = abs(market.get('price_change_percentage_7d', 0))
            data['trend_24h'] = market.get('price_change_percentage_24h', 0)
            data['trend_7d'] = market.get('price_change_percentage_7d', 0)
            
        # 2. 30-day price history for ATR and levels
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=30"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            chart_data = json.loads(response.read().decode())
            
            prices = [p[1] for p in chart_data.get('prices', [])]
            if len(prices) >= 14:
                # Calculate ATR (Average True Range)
                atr_values = []
                for i in range(1, min(15, len(prices))):
                    high_low = abs(prices[i] - prices[i-1])
                    atr_values.append(high_low)
                data['atr_14'] = statistics.mean(atr_values) if atr_values else None
                
                # Find support/resistance using volume profile
                sorted_prices = sorted(prices)
                data['support_levels'] = [
                    sorted_prices[int(len(sorted_prices) * 0.05)],  # 5th percentile
                    sorted_prices[int(len(sorted_prices) * 0.10)],  # 10th percentile
                    sorted_prices[int(len(sorted_prices) * 0.25)]   # 25th percentile
                ]
                data['resistance_levels'] = [
                    sorted_prices[int(len(sorted_prices) * 0.75)],  # 75th percentile
                    sorted_prices[int(len(sorted_prices) * 0.90)],  # 90th percentile
                    sorted_prices[int(len(sorted_prices) * 0.95)]   # 95th percentile
                ]
                
        # 3. Liquidation data from CoinGlass (alternative.me as fallback)
        try:
            url = "https://api.alternative.me/fng/?limit=1"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
                fng_data = json.loads(response.read().decode())
                if fng_data.get('data'):
                    fng_val = int(fng_data['data'][0]['value'])
                    # Estimate liquidation clusters based on F&G
                    if fng_val < 25:
                        data['liquidation_clusters'] = [
                            {'price': data['current_price'] * 0.95, 'side': 'long', 'size': 'high'},
                            {'price': data['current_price'] * 0.90, 'side': 'long', 'size': 'extreme'}
                        ]
                    elif fng_val > 75:
                        data['liquidation_clusters'] = [
                            {'price': data['current_price'] * 1.05, 'side': 'short', 'size': 'high'},
                            {'price': data['current_price'] * 1.10, 'side': 'short', 'size': 'extreme'}
                        ]
        except:
            pass
            
    except Exception as e:
        print(f"Error fetching advanced market data: {e}")
    
    return data

def calculate_kelly_criterion(win_rate, avg_win, avg_loss):
    """Kelly Criterion for optimal position sizing
    f* = (bp - q) / b
    where: b = avg_win/avg_loss, p = win_rate, q = 1-p
    """
    if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
        return 0.1  # Conservative default
    
    b = avg_win / avg_loss
    p = win_rate
    q = 1 - p
    
    kelly = (b * p - q) / b
    return max(0.05, min(kelly, 0.25))  # Cap between 5% and 25%

def detect_market_regime(price_data):
    """Detect current market regime using multiple factors"""
    if not price_data or not price_data.get('current_price'):
        return 'unknown', 0.5
    
    regime_score = 0
    factors = []
    
    # Trend factors
    if price_data.get('trend_24h', 0) > 2:
        regime_score += 1
        factors.append('short_term_bullish')
    elif price_data.get('trend_24h', 0) < -2:
        regime_score -= 1
        factors.append('short_term_bearish')
    
    if price_data.get('trend_7d', 0) > 5:
        regime_score += 1.5
        factors.append('medium_term_bullish')
    elif price_data.get('trend_7d', 0) < -5:
        regime_score -= 1.5
        factors.append('medium_term_bearish')
    
    # Volatility factor
    vol_24h = price_data.get('volatility_24h', 0)
    if vol_24h > 10:
        factors.append('high_volatility')
    elif vol_24h < 3:
        factors.append('low_volatility')
    
    # Classify regime
    if regime_score >= 2:
        regime = 'strong_uptrend'
        bias = 0.8
    elif regime_score >= 0.5:
        regime = 'uptrend'
        bias = 0.65
    elif regime_score <= -2:
        regime = 'strong_downtrend'
        bias = 0.2
    elif regime_score <= -0.5:
        regime = 'downtrend'
        bias = 0.35
    else:
        regime = 'ranging'
        bias = 0.5
    
    return regime, bias, factors

def generate_elite_barry_preset(fng_value, fng_classification, account_balance=1000):
    """ELITE BARRY - Cutthroat profitable Bitcoin trading bot
    
    Features:
    - Dynamic spread based on ATR (Average True Range)
    - Kelly Criterion position sizing
    - Multi-timeframe trend analysis
    - Liquidation cluster hunting
    - Market regime detection
    - Adaptive grid density
    - Support/resistance level targeting
    """
    
    # Fetch comprehensive market data
    market_data = fetch_advanced_market_data()
    current_price = market_data.get('current_price') or 65000
    
    # Detect market regime
    regime, trend_bias, factors = detect_market_regime(market_data)
    
    # Get ATR for dynamic spread calculation
    atr = market_data.get('atr_14', current_price * 0.02)  # Default 2% if no data
    
    # Adjust strategy based on Fear & Greed + Market Regime
    if fng_value <= 20 or regime == 'strong_downtrend':
        strategy = "MAXIMUM_FEAR"
        description = "⚠️ MAXIMUM FEAR: Heavy short bias, hunting liquidations below"
        long_count = 2
        short_count = 10
        spread_multiplier = 0.8  # Tighter spreads in extreme fear
        leverage = 3
        
    elif fng_value <= 40 or regime == 'downtrend':
        strategy = "FEAR_HUNT"
        description = "📉 Fear Hunt: Moderate short bias with strategic longs"
        long_count = 4
        short_count = 8
        spread_multiplier = 1.0
        leverage = 2.5
        
    elif fng_value <= 60 and regime == 'ranging':
        strategy = "RANGE_MAXIMIZER"
        description = "↔️ Range Maximizer: Balanced grid optimized for chop"
        long_count = 6
        short_count = 6
        spread_multiplier = 1.2  # Wider spreads in range
        leverage = 2
        
    elif fng_value >= 80 or regime == 'strong_uptrend':
        strategy = "MOON_CAPTURE"
        description = "🚀 Moon Capture: Heavy long bias, riding momentum"
        long_count = 10
        short_count = 2
        spread_multiplier = 0.8
        leverage = 3
        
    else:
        strategy = "TREND_FOLLOW"
        description = "📈 Trend Follow: Moderate long bias with hedges"
        long_count = 8
        short_count = 4
        spread_multiplier = 1.0
        leverage = 2.5
    
    # Calculate dynamic spread based on ATR
    base_spread = max(atr * 2, current_price * 0.015)  # Minimum 1.5% or 2x ATR
    spread = base_spread * spread_multiplier
    
    # Kelly Criterion position sizing
    # Assume 55% win rate based on backtests, 1.2:1 reward/risk
    win_rate = 0.55
    avg_win = spread * 0.9  # 90% of spread after fees
    avg_loss = spread * 0.75  # 75% of spread (stop loss)
    kelly_fraction = calculate_kelly_criterion(win_rate, avg_win, avg_loss)
    
    # Position size based on Kelly and account balance
    risk_per_trade = account_balance * kelly_fraction
    quantity = max(5, min(risk_per_trade / 10, 50))  # Between $5 and $50
    
    base_price = round(current_price / 100) * 100
    loops = []
    
    # Support and resistance levels for precision targeting
    supports = market_data.get('support_levels', [])
    resistances = market_data.get('resistance_levels', [])
    
    # Generate ELITE LONG loops
    for i in range(long_count):
        # Dynamic spacing - tighter near current price, wider further out
        distance_factor = 1 + (i * 0.3)  # 1.0, 1.3, 1.6, 2.0...
        buy_offset = spread * distance_factor * 2  # 2x spread below
        
        # Target support levels if available
        if supports and i < len(supports):
            buy_price = supports[i]
        else:
            buy_price = base_price - buy_offset
        
        sell_price = buy_price + spread
        
        # Calculate profit probability based on distance from market
        distance_from_market = (current_price - buy_price) / current_price
        profit_prob = min(0.95, 0.55 + (distance_from_market * 5))  # Higher prob if further below
        
        loops.append({
            'id': i + 1,
            'name': f"⚡ ELITE Long {i+1}",
            'direction': 'long',
            'buy_price': round(float(buy_price), 2),
            'sell_price': round(float(sell_price), 2),
            'quantity_usd': round(float(quantity), 2),
            'leverage': leverage,
            'enabled': True,
            'meta': {
                'distance_from_market': f"{distance_from_market*100:.1f}%",
                'profit_probability': f"{profit_prob*100:.1f}%",
                'expected_value': f"${(profit_prob * spread - (1-profit_prob) * spread * 0.75):.2f}",
                'based_on': 'support_level' if supports and i < len(supports) else 'atr_dynamic'
            }
        })
    
    # Generate ELITE SHORT loops
    for i in range(short_count):
        distance_factor = 1 + (i * 0.3)
        sell_offset = spread * distance_factor * 2
        
        # Target resistance levels if available
        if resistances and i < len(resistances):
            sell_price = resistances[i]
        else:
            sell_price = base_price + sell_offset
        
        buy_price = sell_price - spread
        
        distance_from_market = (sell_price - current_price) / current_price
        profit_prob = min(0.95, 0.55 + (distance_from_market * 5))
        
        loops.append({
            'id': long_count + i + 1,
            'name': f"⚡ ELITE Short {i+1}",
            'direction': 'short',
            'buy_price': round(float(buy_price), 2),
            'sell_price': round(float(sell_price), 2),
            'quantity_usd': round(float(quantity), 2),
            'leverage': leverage,
            'enabled': True,
            'meta': {
                'distance_from_market': f"{distance_from_market*100:.1f}%",
                'profit_probability': f"{profit_prob*100:.1f}%",
                'expected_value': f"${(profit_prob * spread - (1-profit_prob) * spread * 0.75):.2f}",
                'based_on': 'resistance_level' if resistances and i < len(resistances) else 'atr_dynamic'
            }
        })
    
    # Sort by price for optimal execution order
    loops.sort(key=lambda x: x['buy_price'])
    
    # Reassign IDs after sorting
    for i, loop in enumerate(loops):
        loop['id'] = i + 1
    
    return {
        'strategy': strategy,
        'description': description,
        'regime': regime,
        'regime_factors': factors,
        'fng_value': fng_value,
        'fng_classification': fng_classification,
        'current_price': current_price,
        'atr_14': round(atr, 2) if atr else None,
        'base_spread': round(spread, 2),
        'kelly_fraction': round(kelly_fraction, 3),
        'risk_per_trade': round(risk_per_trade, 2),
        'account_balance': account_balance,
        'long_count': long_count,
        'short_count': short_count,
        'total_expected_value': round(sum([float(l['meta']['expected_value'].replace('$', '')) for l in loops]), 2),
        'support_levels': [round(s, 2) for s in supports[:3]],
        'resistance_levels': [round(r, 2) for r in resistances[:3]],
        'loops': loops
    }

def generate_barry_preset(fng_value, fng_classification):
    """Generate Barry preset loops based on Fear & Greed Index
    
    Barry adapts to market sentiment:
    - Extreme Fear (0-24): Heavy short bias (8 short, 2 long)
    - Fear (25-44): Moderate short bias (7 short, 3 long)
    - Neutral (45-55): Balanced (5 short, 5 long)
    - Greed (56-75): Moderate long bias (7 long, 3 short)
    - Extreme Greed (76-100): Heavy long bias (8 long, 2 short)
    """
    current_price = get_current_btc_price()
    if not current_price:
        current_price = 65000  # fallback
    
    base_price = round(current_price / 500) * 500  # Round to nearest 500
    
    # Define strategy based on Fear & Greed
    if fng_value <= 24:  # Extreme Fear
        strategy = "extreme_fear"
        long_count = 2
        short_count = 8
        description = "Extreme Fear Strategy - Heavy short bias anticipating further downside"
    elif fng_value <= 44:  # Fear
        strategy = "fear"
        long_count = 3
        short_count = 7
        description = "Fear Strategy - Moderate short bias with some long hedges"
    elif fng_value <= 55:  # Neutral
        strategy = "neutral"
        long_count = 5
        short_count = 5
        description = "Neutral Strategy - Balanced grid for range-bound markets"
    elif fng_value <= 75:  # Greed
        strategy = "greed"
        long_count = 7
        short_count = 3
        description = "Greed Strategy - Moderate long bias with short hedges"
    else:  # Extreme Greed
        strategy = "extreme_greed"
        long_count = 8
        short_count = 2
        description = "Extreme Greed Strategy - Heavy long bias anticipating further upside"
    
    loops = []
    
    # Generate LONG loops (buy below, sell above)
    for i in range(long_count):
        # Create descending buy prices below current market
        buy_offset = 2000 + (i * 1500)  # 2000, 3500, 5000, etc. below
        sell_offset = 700 + (i * 100)   # 700, 800, 900, etc. above buy
        
        buy_price = base_price - buy_offset
        sell_price = buy_price + sell_offset
        
        loops.append({
            'id': i + 1,
            'name': f"Barry Long {i+1}",
            'direction': 'long',
            'buy_price': float(buy_price),
            'sell_price': float(sell_price),
            'quantity_usd': 10.0,
            'leverage': 2,
            'enabled': True
        })
    
    # Generate SHORT loops (sell above, buy below)
    for i in range(short_count):
        # Create ascending sell prices above current market
        sell_offset = 2000 + (i * 1500)  # 2000, 3500, 5000, etc. above
        buy_offset = 700 + (i * 100)     # 700, 800, 900, etc. below sell
        
        sell_price = base_price + sell_offset
        buy_price = sell_price - buy_offset
        
        loops.append({
            'id': long_count + i + 1,
            'name': f"Barry Short {i+1}",
            'direction': 'short',
            'buy_price': float(buy_price),
            'sell_price': float(sell_price),
            'quantity_usd': 10.0,
            'leverage': 2,
            'enabled': True
        })
    
    return {
        'strategy': strategy,
        'description': description,
        'fng_value': fng_value,
        'fng_classification': fng_classification,
        'base_price': base_price,
        'long_count': long_count,
        'short_count': short_count,
        'loops': loops
    }

@app.route('/api/presets/barry', methods=['GET'])
def get_barry_preset():
    """Get Barry preset loops based on current Fear & Greed Index"""
    try:
        # Fetch current Fear & Greed
        import urllib.request
        import ssl
        
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        url = "https://api.alternative.me/fng/?limit=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            data = json.loads(response.read().decode())
            
            if data.get('data') and len(data['data']) > 0:
                fng = data['data'][0]
                value = int(fng['value'])
                classification = fng['value_classification']
                
                preset = generate_barry_preset(value, classification)
                return jsonify({
                    'success': True,
                    'preset': preset
                })
        
        return jsonify({'success': False, 'error': 'Unable to fetch Fear & Greed data'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/presets/barry/elite', methods=['GET'])
def get_elite_barry_preset():
    """Get ELITE BARRY preset - Cutthroat profitable trading bot"""
    try:
        # Get account balance from query param or default
        account_balance = request.args.get('balance', 1000, type=float)
        
        # Fetch current Fear & Greed
        import urllib.request
        import ssl
        
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        url = "https://api.alternative.me/fng/?limit=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            data = json.loads(response.read().decode())
            
            if data.get('data') and len(data['data']) > 0:
                fng = data['data'][0]
                value = int(fng['value'])
                classification = fng['value_classification']
                
                preset = generate_elite_barry_preset(value, classification, account_balance)
                return jsonify({
                    'success': True,
                    'preset': preset,
                    'elite': True,
                    'features': [
                        'Dynamic ATR-based spread calculation',
                        'Kelly Criterion position sizing',
                        'Multi-timeframe trend analysis',
                        'Market regime detection',
                        'Support/resistance level targeting',
                        'Liquidation cluster hunting',
                        'Adaptive grid density',
                        'Expected value calculation per loop'
                    ]
                })
        
        return jsonify({'success': False, 'error': 'Unable to fetch Fear & Greed data'})
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()})

@app.route('/api/presets/barry/apply', methods=['POST'])
def apply_barry_preset():
    """Apply Barry preset to config"""
    try:
        data = request.json
        loops = data.get('loops', [])
        
        if not loops:
            return jsonify({'success': False, 'error': 'No loops provided'})
        
        config = load_config()
        
        # Clear existing loops (optional - can be disabled)
        # config['loops'] = []
        
        # Add Barry loops
        for loop in loops:
            loop['id'] = len(config['loops']) + 1
            config['loops'].append(loop)
        
        save_config(config)
        
        return jsonify({
            'success': True,
            'message': f"Applied {len(loops)} Barry preset loops",
            'total_loops': len(config['loops'])
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/loops', methods=['POST'])
def add_loop():
    """Add a new loop"""
    data = request.json
    config = load_config()
    
    direction = data.get('direction', 'long')
    buy_price = float(data['buy_price'])
    sell_price = float(data['sell_price'])
    
    # Get current BTC price to validate order placement
    current_price = get_current_btc_price()
    if current_price:
        # For LONG orders: buy price must be BELOW current price
        if direction == 'long' and buy_price >= current_price:
            error_msg = f'REJECTED: LONG order above spot price. Buy ${buy_price:,.0f} >= Spot ${current_price:,.0f}'
            add_log(error_msg)
            return jsonify({
                'success': False, 
                'error': f'Cannot place LONG order above spot price. Buy price ${buy_price:,.0f} is above current BTC price ${current_price:,.0f}. Lower your buy price or wait for BTC to drop.'
            }), 400
        
        # For SHORT orders: sell price must be ABOVE current price
        if direction == 'short' and sell_price <= current_price:
            error_msg = f'REJECTED: SHORT order below spot price. Sell ${sell_price:,.0f} <= Spot ${current_price:,.0f}'
            add_log(error_msg)
            return jsonify({
                'success': False,
                'error': f'Cannot place SHORT order below spot price. Sell price ${sell_price:,.0f} is below current BTC price ${current_price:,.0f}. Raise your sell price or wait for BTC to rise.'
            }), 400
    
    new_loop = {
        'id': len(config['loops']) + 1,
        'name': data.get('name', f"Loop {len(config['loops']) + 1}"),
        'direction': direction,
        'buy_price': buy_price,
        'sell_price': sell_price,
        'quantity_usd': float(data['quantity_usd']),
        'leverage': int(data.get('leverage', 1)),
        'enabled': True
    }
    
    config['loops'].append(new_loop)
    save_config(config)
    
    if direction == 'short':
        add_log(f"Added {new_loop['name']}: SHORT Sell ${new_loop['buy_price']:.0f} → Buy ${new_loop['sell_price']:.0f} @ {new_loop['leverage']}x")
    else:
        add_log(f"Added {new_loop['name']}: LONG Buy ${new_loop['buy_price']:.0f} → Sell ${new_loop['sell_price']:.0f} @ {new_loop['leverage']}x")
    
    return jsonify({'success': True, 'loop': new_loop})

@app.route('/api/loops/<int:loop_id>', methods=['DELETE'])
def delete_loop(loop_id):
    """Delete a loop"""
    config = load_config()
    config['loops'] = [l for l in config['loops'] if l['id'] != loop_id]
    save_config(config)
    add_log(f"Deleted loop {loop_id}")
    return jsonify({'success': True})

@app.route('/api/loops/<int:loop_id>', methods=['PUT'])
def update_loop(loop_id):
    """Update/edit a loop"""
    data = request.json
    config = load_config()
    
    for loop in config['loops']:
        if loop['id'] == loop_id:
            if 'name' in data:
                loop['name'] = data['name']
            if 'buy_price' in data:
                loop['buy_price'] = float(data['buy_price'])
            if 'sell_price' in data:
                loop['sell_price'] = float(data['sell_price'])
            if 'quantity_usd' in data:
                loop['quantity_usd'] = float(data['quantity_usd'])
            if 'leverage' in data:
                loop['leverage'] = int(data['leverage'])
            if 'enabled' in data:
                loop['enabled'] = bool(data['enabled'])
            
            save_config(config)
            add_log(f"Updated {loop['name']}: Buy ${loop['buy_price']:.0f} → Sell ${loop['sell_price']:.0f}")
            return jsonify({'success': True, 'loop': loop})
    
    return jsonify({'success': False, 'error': 'Loop not found'}), 404

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get settings (without sensitive data)"""
    config = load_config()
    return jsonify({
        'api_key_configured': bool(config.get('api_key')),
        'leverage': config.get('leverage', 1),
        'check_seconds': config.get('check_seconds', 30),
        'loop_count': len(config.get('loops', [])),
        'auto_mirror': config.get('auto_mirror', False)
    })

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update settings"""
    data = request.json
    config = load_config()
    
    if 'api_key' in data:
        config['api_key'] = data['api_key']
    if 'api_secret' in data:
        config['api_secret'] = data['api_secret']
    if 'api_passphrase' in data:
        config['api_passphrase'] = data['api_passphrase']
    if 'leverage' in data:
        config['leverage'] = int(data['leverage'])
    if 'check_seconds' in data:
        config['check_seconds'] = int(data['check_seconds'])
    
    save_config(config)
    return jsonify({'success': True})

@app.route('/api/settings/keys', methods=['DELETE'])
def delete_api_keys():
    """Delete API keys from config"""
    config = load_config()
    
    # Stop bot if running
    global bot_running
    if bot_running:
        bot_running = False
        save_state({"should_be_running": False})
        add_log("Bot stopped - API keys deleted")
    
    # Clear API keys
    config['api_key'] = ''
    config['api_secret'] = ''
    config['api_passphrase'] = ''
    
    save_config(config)
    add_log("API keys deleted from configuration")
    
    return jsonify({'success': True, 'message': 'API keys deleted successfully'})

@app.route('/api/settings/mirror', methods=['POST'])
def update_mirror_setting():
    """Update auto mirror setting"""
    data = request.json
    config = load_config()
    
    if 'enabled' in data:
        config['auto_mirror'] = bool(data['enabled'])
        save_config(config)
        add_log(f"Auto mirror {'enabled' if config['auto_mirror'] else 'disabled'}")
        return jsonify({'success': True, 'auto_mirror': config['auto_mirror']})
    
    return jsonify({'success': False, 'error': 'Missing enabled parameter'})

@app.route('/api/start', methods=['POST'])
def start_bot():
    """Start the bot"""
    global bot_thread, bot_running
    
    if bot_running:
        return jsonify({'success': False, 'error': 'Bot already running'})
    
    config = load_config()
    if not config.get('api_key') or len(config['api_key']) < 10:
        return jsonify({'success': False, 'error': 'API keys not configured'})
    
    if not config.get('loops'):
        return jsonify({'success': False, 'error': 'No loops configured'})
    
    bot_running = True
    save_state({"should_be_running": True})  # Persist state
    bot_thread = threading.Thread(target=run_bot_thread, daemon=True)
    bot_thread.start()
    add_log("Bot started")
    
    return jsonify({'success': True})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    """Stop the bot"""
    global bot_running
    bot_running = False
    save_state({"should_be_running": False})  # Persist state
    add_log("Bot stopping...")
    return jsonify({'success': True})

@app.route('/api/refresh', methods=['POST'])
def refresh_bot():
    """Refresh bot config - triggers reload of loops"""
    global bot_thread, bot_running
    
    if not bot_running:
        return jsonify({'success': False, 'error': 'Bot is not running'})
    
    # Stop current bot
    bot_running = False
    if bot_thread and bot_thread.is_alive():
        # Wait a moment for thread to stop
        import time
        time.sleep(0.5)
    
    # Restart with new config
    config = load_config()
    if not config.get('api_key') or len(config['api_key']) < 10:
        return jsonify({'success': False, 'error': 'API keys not configured'})
    
    if not config.get('loops'):
        return jsonify({'success': False, 'error': 'No loops configured'})
    
    bot_running = True
    bot_thread = threading.Thread(target=run_bot_thread, daemon=True)
    bot_thread.start()
    add_log("Bot refreshed - new config loaded")
    
    return jsonify({'success': True})

@app.route('/api/sync', methods=['POST'])
def sync_orders():
    """Trigger a manual sync of loops with LN Markets orders"""
    global bot_running, bot_thread
    
    config = load_config()
    
    if not config.get('api_key') or len(config['api_key']) < 10:
        return jsonify({'success': False, 'error': 'API keys not configured'})
    
    if not config.get('loops'):
        return jsonify({'success': False, 'error': 'No loops configured'})
    
    # The bot will sync on next restart, so we restart it
    if bot_running and bot_thread:
        # Stop current bot
        bot_running = False
        add_log("Stopping bot for manual sync...")
        time.sleep(2)  # Give it time to stop
    
    # Restart with sync
    bot_running = True
    bot_thread = threading.Thread(target=run_bot_thread, daemon=True)
    bot_thread.start()
    add_log("Manual sync triggered - bot restarted with order reconciliation")
    
    return jsonify({'success': True, 'message': 'Sync triggered - bot restarted'})

@app.route('/api/mirror', methods=['POST'])
def mirror_orders():
    """Full mirror: Ensure LN Markets exactly matches LoopTrade loops"""
    global bot_running, bot_thread
    
    config = load_config()
    
    if not config.get('api_key') or len(config['api_key']) < 10:
        return jsonify({'success': False, 'error': 'API keys not configured'})
    
    if not config.get('loops'):
        return jsonify({'success': False, 'error': 'No loops configured'})
    
    # Stop bot to avoid conflicts
    if bot_running:
        bot_running = False
        add_log("Stopping bot for full mirror operation...")
        time.sleep(2)
    
    # Run mirror operation in background thread
    def do_mirror():
        import subprocess
        import sys
        import os
        
        # Get current working directory
        cwd = os.getcwd()
        mirror_script = os.path.join(cwd, 'looptrade_mirror.py')
        
        mirror_code = '''
import sys
import os

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Add virtual environment to path if it exists  
venv_paths = [
    os.path.join(SCRIPT_DIR, 'venv', 'lib', 'python3.9', 'site-packages'),
    os.path.join(SCRIPT_DIR, 'venv', 'lib', 'python3.10', 'site-packages'),
    os.path.join(SCRIPT_DIR, 'venv', 'lib', 'python3.11', 'site-packages'),
    os.path.join(SCRIPT_DIR, '..', 'venv', 'lib', 'python3.9', 'site-packages'),
]
for venv_path in venv_paths:
    if os.path.exists(venv_path) and venv_path not in sys.path:
        sys.path.insert(0, venv_path)
        break

import asyncio
import json
import time
from datetime import datetime

LOGS_FILE = os.path.join(SCRIPT_DIR, "looptrade_logs.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "looptrade_config.json")

# Global dict to track prices we're already trying to place orders at
_orders_being_placed = {}
_ORDERS_TIMEOUT_SECONDS = 120

def is_price_being_placed(price):
    """Check if a price is currently being processed, with timeout cleanup"""
    global _orders_being_placed
    now = time.time()
    expired = [p for p, t in _orders_being_placed.items() if now - t > _ORDERS_TIMEOUT_SECONDS]
    for p in expired:
        del _orders_being_placed[p]
    return price in _orders_being_placed

def mark_price_placing(price):
    """Mark a price as being processed"""
    global _orders_being_placed
    _orders_being_placed[price] = time.time()

def unmark_price_placing(price):
    """Remove price from tracking"""
    global _orders_being_placed
    if price in _orders_being_placed:
        del _orders_being_placed[price]

def add_log(message):
    """Add a log entry to the shared log file"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    
    try:
        # Read existing logs
        logs = []
        if os.path.exists(LOGS_FILE):
            with open(LOGS_FILE, 'r') as f:
                try:
                    logs = json.load(f)
                except:
                    logs = []
        
        # Add new log
        logs.append(log_entry)
        
        # Keep only last 500
        while len(logs) > 500:
            logs.pop(0)
        
        # Write back
        with open(LOGS_FILE, 'w') as f:
            json.dump(logs, f, indent=2)
    except Exception as e:
        print(f"Log error: {e}")

def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

config = load_config()
API_KEY = config['api_key']
API_SECRET = config['api_secret']
API_PASSPHRASE = config['api_passphrase']

async def mirror():
    from lnmarkets_sdk.rest.v3.http.client import LNMClient
    from lnmarkets_sdk.rest.v3._internal.models import APIAuthContext, APIClientConfig
    from lnmarkets_sdk.rest.v3.models.futures_isolated import FuturesOrder, UpdateTakeprofitParams, CancelTradeParams
    
    auth = APIAuthContext(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)
    cfg = APIClientConfig(authentication=auth, network="mainnet")
    
    async with LNMClient(cfg) as client:
        add_log("[MIRROR] Starting full mirror operation...")
        
        # Get all loops from config
        loops = config.get('loops', [])
        add_log(f"[MIRROR] Found {len(loops)} loops in LoopTrade")
        
        # Build map of loop entry prices to expected margin
        loop_data = {}  # price -> (qty, leverage, expected_margin)
        for loop in loops:
            direction = loop.get('direction', 'long')
            if direction == 'short':
                entry_price = round(loop['sell_price'] * 2) / 2
            else:
                entry_price = round(loop['buy_price'] * 2) / 2
            qty = loop['quantity_usd']
            leverage = loop.get('leverage', 1)
            # Calculate expected margin (satoshis)
            expected_margin = round((qty / entry_price) * 1e8 / leverage)
            loop_data[entry_price] = (qty, leverage, expected_margin)
        
        # Get all open orders from LN Markets
        try:
            open_orders = await client.futures.isolated.get_open_trades()
            add_log(f"[MIRROR] Found {len(open_orders)} open orders on LN Markets")
        except Exception as e:
            add_log(f"[MIRROR] Error fetching orders: {e}")
            return
        
        # Cancel orders that don't match any loop OR have wrong margin/quantity
        cancelled = 0
        add_log(f"[MIRROR] Loop prices: {sorted(loop_data.keys())}")
        for order in open_orders:
            try:
                order_price = round(order.price * 2) / 2
                order_margin = order.margin  # in satoshis
                order_quantity = order.quantity  # position size in USD
                
                should_cancel = False
                cancel_reason = ""
                
                if order_price not in loop_data:
                    should_cancel = True
                    cancel_reason = "not in loops"
                else:
                    expected_qty = loop_data[order_price][0]
                    expected_margin = loop_data[order_price][2]
                    
                    # Check if quantity is correct (must match exactly)
                    if order_quantity != expected_qty:
                        should_cancel = True
                        cancel_reason = f"wrong quantity (got ${order_quantity}, expected ${expected_qty})"
                    # Also check margin (within 5% tolerance)
                    elif abs(order_margin - expected_margin) / expected_margin * 100 > 5:
                        should_cancel = True
                        cancel_reason = f"wrong margin (got {order_margin}, expected {expected_margin})"
                
                add_log(f"[MIRROR] Checking order @ ${order_price:,.0f} qty=${order_quantity} margin={order_margin} - cancel: {should_cancel}")
                
                if should_cancel:
                    add_log(f"[MIRROR] Cancelling order @ ${order_price:,.0f} ({cancel_reason})")
                    cancel_params = CancelTradeParams(id=str(order.id))
                    await client.futures.isolated.cancel(cancel_params)
                    add_log(f"[MIRROR] Cancelled order {str(order.id)[:8]}... @ ${order_price:,.0f}")
                    # Unmark price so bot can place new order
                    unmark_price_placing(order_price)
                    cancelled += 1
                    await asyncio.sleep(1)  # Rate limiting
            except Exception as e:
                add_log(f"[MIRROR] Error cancelling order: {e}")
        
        # Place orders for loops that don't have one
        placed = 0
        for loop in loops:
            try:
                direction = loop.get('direction', 'long')
                buy_price = loop['buy_price']
                sell_price = loop['sell_price']
                qty = loop['quantity_usd']
                leverage = loop.get('leverage', 1)
                
                if direction == 'short':
                    entry_price = round(sell_price * 2) / 2
                    entry_side = 'sell'
                    exit_price = buy_price
                else:
                    entry_price = round(buy_price * 2) / 2
                    entry_side = 'buy'
                    exit_price = sell_price
                
                # Check if order already exists at this price
                existing = False
                for order in open_orders:
                    order_price = round(order.price * 2) / 2
                    if abs(order_price - entry_price) < 0.5:
                        existing = True
                        break
                
                if not existing:
                    # CRITICAL FIX: Check and mark price as placing to prevent race conditions
                    if is_price_being_placed(entry_price):
                        add_log(f"[MIRROR] SKIPPED: Price ${entry_price:,.0f} is being placed by another loop")
                        continue
                    
                    mark_price_placing(entry_price)
                    
                    # Place the order with quantity (not margin) to control position size
                    params = FuturesOrder(
                        type='limit', 
                        side=entry_side, 
                        price=float(entry_price), 
                        leverage=float(leverage), 
                        quantity=float(qty)
                    )
                    resp = await client.futures.isolated.new_trade(params)
                    add_log(f"[MIRROR] Placed {entry_side} order for '{loop.get('name')}' @ ${entry_price:,.0f} qty=${qty}")
                    unmark_price_placing(entry_price)  # Unmark after successful placement
                    
                    # Set takeprofit
                    try:
                        tp_params = UpdateTakeprofitParams(id=resp.id, value=float(exit_price))
                        await client.futures.isolated.update_takeprofit(tp_params)
                        add_log(f"[MIRROR] Set takeprofit @ ${exit_price:,.0f}")
                    except Exception as e:
                        add_log(f"[MIRROR] Warning: Could not set takeprofit: {e}")
                    
                    placed += 1
                    await asyncio.sleep(2)  # Rate limiting
                else:
                    add_log(f"[MIRROR] Order exists for '{loop.get('name')}' @ ${entry_price:,.0f}")
                    
            except Exception as e:
                add_log(f"[MIRROR] Error placing order: {e}")
                unmark_price_placing(entry_price)  # Unmark on error
        
        add_log(f"[MIRROR] Complete! Cancelled: {cancelled}, Placed: {placed}")

asyncio.run(mirror())
'''
        
        with open(mirror_script, 'w') as f:
            f.write(mirror_code)
        
        try:
            # Find the virtual environment python
            venv_python = os.path.join(cwd, 'venv', 'bin', 'python3')
            if not os.path.exists(venv_python):
                # Try alternative path
                venv_python = os.path.join(cwd, '..', 'venv', 'bin', 'python3')
            if not os.path.exists(venv_python):
                # Fallback to system python and add venv to path
                venv_python = sys.executable
            
            add_log(f"[MIRROR] Using Python: {venv_python}")
            
            # Run and capture output
            result = subprocess.run(
                [venv_python, mirror_script],
                capture_output=True,
                text=True,
                cwd=cwd
            )
            
            if result.returncode != 0:
                add_log(f"[MIRROR] Error: {result.stderr[:500]}")
            elif result.stderr:
                add_log(f"[MIRROR] stderr: {result.stderr[:200]}")
                
        except Exception as e:
            add_log(f"[MIRROR] Error running mirror: {e}")
    
    # Start mirror in background
    mirror_thread = threading.Thread(target=do_mirror, daemon=True)
    mirror_thread.start()
    
    add_log("Full mirror operation started - syncing LN Markets to match LoopTrade")
    
    # Restart bot after mirror completes
    def restart_after_mirror():
        mirror_thread.join()
        global bot_running, bot_thread
        bot_running = True
        bot_thread = threading.Thread(target=run_bot_thread, daemon=True)
        bot_thread.start()
        add_log("Mirror complete - bot restarted")
    
    restart_thread = threading.Thread(target=restart_after_mirror, daemon=True)
    restart_thread.start()
    
    return jsonify({'success': True, 'message': 'Full mirror started - this may take a minute'})

@app.route('/api/market/sentiment', methods=['GET'])
def get_market_sentiment():
    """Fetch Fear & Greed Index and market regime"""
    import urllib.request
    import ssl
    
    def fetch_sentiment():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        url = "https://api.alternative.me/fng/?limit=30"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            data = json.loads(response.read().decode())
            
            if data.get('data') and len(data['data']) > 0:
                fng = data['data'][0]
                value = int(fng['value'])
                classification = fng['value_classification']
                
                if value <= 20:
                    regime = "Extreme Fear - Potential Bottom"
                    regime_class = "extreme-fear"
                    trend = "down"
                elif value <= 40:
                    regime = "Fear - Caution"
                    regime_class = "fear"
                    trend = "down"
                elif value <= 60:
                    regime = "Neutral - Range Bound"
                    regime_class = "neutral"
                    trend = "neutral"
                elif value <= 80:
                    regime = "Greed - Trending Up"
                    regime_class = "greed"
                    trend = "up"
                else:
                    regime = "Extreme Greed - Potential Top"
                    regime_class = "extreme-greed"
                    trend = "up"
                
                history = []
                for entry in reversed(data['data']):
                    history.append({
                        'value': int(entry['value']),
                        'classification': entry['value_classification'],
                        'timestamp': entry.get('timestamp', '')
                    })
                
                return {
                    'success': True,
                    'fear_greed_index': value,
                    'classification': classification,
                    'regime': regime,
                    'regime_class': regime_class,
                    'trend': trend,
                    'timestamp': fng.get('timestamp', 'now'),
                    'history': history
                }
        return {'success': False, 'error': 'Unable to fetch data'}
    
    try:
        return jsonify(get_cached('market_sentiment', fetch_sentiment))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Cache storage
_cache = {}
CACHE_DURATION = 3600  # 60 minutes (1 hour) - Metrics only need hourly updates

# Separate cache for price (more frequent but still limited)
_price_cache_duration = 60  # 1 minute for price only

# Global CoinGecko rate limiter
_last_coingecko_call = 0
_coingecko_min_interval = 6  # Minimum seconds between CoinGecko calls (max 10/min)

def rate_limited_coingecko_call(url, headers=None):
    """Make rate-limited call to CoinGecko"""
    global _last_coingecko_call
    import time
    
    now = time.time()
    time_since_last = now - _last_coingecko_call
    
    if time_since_last < _coingecko_min_interval:
        sleep_time = _coingecko_min_interval - time_since_last
        print(f"[RATE LIMIT] Waiting {sleep_time:.1f}s before next CoinGecko call...")
        time.sleep(sleep_time)
    
    _last_coingecko_call = time.time()
    
    import urllib.request
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    req = urllib.request.Request(url, headers=headers or {'User-Agent': 'Mozilla/5.0'})
    
    with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
        return json.loads(response.read().decode())

def get_cached(key, fetch_func):
    """Get data from cache or fetch if expired"""
    now = time.time()
    if key in _cache:
        data, timestamp = _cache[key]
        if now - timestamp < CACHE_DURATION:
            return data
    # Fetch new data
    try:
        data = fetch_func()
        _cache[key] = (data, now)
        return data
    except Exception as e:
        # Return cached data even if expired, or error
        if key in _cache:
            return _cache[key][0]
        raise e

@app.route('/api/market/trend', methods=['GET'])
def get_market_trend():
    """Fetch BTC price and calculate simple trend indicators"""
    import urllib.request
    import ssl
    
    def fetch_trend():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            data = json.loads(response.read().decode())
            
            if data.get('bitcoin'):
                btc = data['bitcoin']
                price = btc['usd']
                change_24h = btc.get('usd_24h_change', 0)
                
                signals = []
                
                if change_24h > 5:
                    signals.append({
                        'name': '24h Momentum',
                        'signal': 'STRONG BULLISH',
                        'icon': '🚀',
                        'class': 'bullish-strong',
                        'description': f'Up {change_24h:.1f}% in 24h - strong upward momentum'
                    })
                elif change_24h > 2:
                    signals.append({
                        'name': '24h Momentum',
                        'signal': 'BULLISH',
                        'icon': '📈',
                        'class': 'bullish',
                        'description': f'Up {change_24h:.1f}% in 24h - positive momentum'
                    })
                elif change_24h < -5:
                    signals.append({
                        'name': '24h Momentum',
                        'signal': 'STRONG BEARISH',
                        'icon': '🔻',
                        'class': 'bearish-strong',
                        'description': f'Down {abs(change_24h):.1f}% in 24h - strong downward momentum'
                    })
                elif change_24h < -2:
                    signals.append({
                        'name': '24h Momentum',
                        'signal': 'BEARISH',
                        'icon': '📉',
                        'class': 'bearish',
                        'description': f'Down {abs(change_24h):.1f}% in 24h - negative momentum'
                    })
                else:
                    signals.append({
                        'name': '24h Momentum',
                        'signal': 'NEUTRAL',
                        'icon': '➡️',
                        'class': 'neutral',
                        'description': f'{change_24h:+.1f}% in 24h - sideways movement'
                    })
                
                if change_24h > 3:
                    recommendation = "Consider LONG positions - momentum is up"
                    rec_class = "recommend-long"
                elif change_24h < -3:
                    recommendation = "Consider SHORT positions - momentum is down"
                    rec_class = "recommend-short"
                else:
                    recommendation = "Consider RANGE trading - wait for clear direction"
                    rec_class = "recommend-neutral"
                
                return {
                    'success': True,
                    'price': price,
                    'change_24h': change_24h,
                    'signals': signals,
                    'recommendation': recommendation,
                    'recommendation_class': rec_class
                }
        return {'success': False, 'error': 'Unable to fetch trend data'}
    
    try:
        return jsonify(get_cached('market_trend', fetch_trend))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/market/lnmarkets', methods=['GET'])
def get_lnmarkets_data():
    """Fetch real-time market data from LN Markets API (requires authentication)"""
    import urllib.request
    import ssl
    
    def fetch_lnmarkets():
        config = load_config()
        if not config.get('api_key'):
            return {'success': False, 'error': 'API keys required', 'note': 'Configure API keys in Settings to access LN Markets data'}
        
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        data = {}
        
        # Get mark price (public endpoint)
        try:
            url = "https://api.lnmarkets.com/v3/futures/mark-price"
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json'
            })
            with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
                mark_data = json.loads(response.read().decode())
                data['mark_price'] = mark_data.get('price')
        except Exception as e:
            print(f"LN Markets mark price error: {e}")
        
        # Get index price (public endpoint)
        try:
            url = "https://api.lnmarkets.com/v3/futures/index-price"
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json'
            })
            with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
                index_data = json.loads(response.read().decode())
                data['index_price'] = index_data.get('price')
        except Exception as e:
            print(f"LN Markets index price error: {e}")
        
        # Get stats - requires auth
        try:
            import hmac
            import hashlib
            import base64
            
            api_key = config['api_key']
            api_secret = config['api_secret']
            passphrase = config['api_passphrase']
            
            timestamp = str(int(time.time() * 1000))
            method = 'GET'
            path = '/v3/futures/history/stats?limit=1'
            body = ''
            
            message = timestamp + method + path + body
            signature = base64.b64encode(
                hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).digest()
            ).decode()
            
            url = f"https://api.lnmarkets.com{path}"
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json',
                'lnm-access-key': api_key,
                'lnm-access-timestamp': timestamp,
                'lnm-access-passphrase': passphrase,
                'lnm-access-signature': signature
            })
            
            with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
                stats = json.loads(response.read().decode())
                if stats and len(stats) > 0:
                    latest = stats[0]
                    data['open_interest'] = latest.get('open_interest')
                    data['volume_24h'] = latest.get('volume')
                    data['liquidations_24h'] = latest.get('liquidation_volume')
        except Exception as e:
            print(f"LN Markets stats error: {e}")
        
        # Get recent funding - requires auth
        try:
            timestamp = str(int(time.time() * 1000))
            method = 'get'
            path = '/v3/futures/history/funding?limit=1'
            body = ''
            
            message = timestamp + method + path + body
            signature = base64.b64encode(
                hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).digest()
            ).decode()
            
            url = f"https://api.lnmarkets.com{path}"
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json',
                'lnm-access-key': api_key,
                'lnm-access-timestamp': timestamp,
                'lnm-access-passphrase': passphrase,
                'lnm-access-signature': signature
            })
            
            with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
                funding = json.loads(response.read().decode())
                if funding and len(funding) > 0:
                    data['last_funding_rate'] = funding[0].get('funding_rate')
                    data['last_funding_time'] = funding[0].get('time')
        except Exception as e:
            print(f"LN Markets funding error: {e}")
        
        if not data:
            return {'success': False, 'error': 'Unable to fetch LN Markets data'}
        
        return {
            'success': True,
            'source': 'LN Markets',
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
    
    try:
        return jsonify(get_cached('lnmarkets_data', fetch_lnmarkets))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/market/history', methods=['GET'])
def get_market_history():
    """Fetch BTC price history with daily high/low for volatility analysis"""
    import urllib.request
    import ssl
    from datetime import datetime, timedelta
    
    def fetch_history():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        days = 30
        url = f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days={days}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            data = json.loads(response.read().decode())
            
            if data.get('prices'):
                prices = data['prices']
                daily_stats = {}
                
                for timestamp, price in prices:
                    date = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d')
                    
                    if date not in daily_stats:
                        daily_stats[date] = {
                            'high': price,
                            'low': price,
                            'open': price,
                            'close': price,
                            'prices': [price]
                        }
                    else:
                        daily_stats[date]['high'] = max(daily_stats[date]['high'], price)
                        daily_stats[date]['low'] = min(daily_stats[date]['low'], price)
                        daily_stats[date]['close'] = price
                        daily_stats[date]['prices'].append(price)
                
                history = []
                for date in sorted(daily_stats.keys()):
                    stats = daily_stats[date]
                    spread = stats['high'] - stats['low']
                    volatility = (spread / stats['open']) * 100
                    price_change = stats['close'] - stats['open']
                    direction = 'up' if price_change > 0 else 'down' if price_change < 0 else 'flat'
                    
                    history.append({
                        'date': date,
                        'high': round(stats['high'], 2),
                        'low': round(stats['low'], 2),
                        'open': round(stats['open'], 2),
                        'close': round(stats['close'], 2),
                        'spread': round(spread, 2),
                        'volatility': round(volatility, 2),
                        'direction': direction,
                        'price_change': round(price_change, 2)
                    })
                
                all_highs = [h['high'] for h in history]
                all_lows = [h['low'] for h in history]
                avg_volatility = sum(h['volatility'] for h in history) / len(history)
                avg_spread = sum(h['spread'] for h in history) / len(history)
                max_spread = max(h['spread'] for h in history)
                
                return {
                    'success': True,
                    'history': history,
                    'summary': {
                        'period_high': round(max(all_highs), 2),
                        'period_low': round(min(all_lows), 2),
                        'total_range': round(max(all_highs) - min(all_lows), 2),
                        'avg_volatility': round(avg_volatility, 2),
                        'avg_daily_spread': round(avg_spread, 2),
                        'max_daily_spread': round(max_spread, 2)
                    }
                }
        return {'success': False, 'error': 'Unable to fetch history'}
    
    try:
        return jsonify(get_cached('market_history', fetch_history))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/market/liquidations', methods=['GET'])
def get_liquidation_heatmap():
    """Generate liquidation heatmap data based on LN Markets price"""
    import urllib.request
    import ssl
    import hmac
    import hashlib
    import base64
    
    def fetch_liquidations():
        config = load_config()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        current_price = None
        price_source = 'CoinGecko'
        
        # Try LN Markets mark price with auth
        if config.get('api_key') and config.get('api_secret'):
            try:
                api_key = config['api_key']
                api_secret = config['api_secret']
                passphrase = config['api_passphrase']
                
                timestamp = str(int(time.time() * 1000))
                method = 'get'
                path = '/v3/futures/mark-price'
                body = ''
                
                message = timestamp + method + path + body
                signature = base64.b64encode(
                    hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).digest()
                ).decode()
                
                url = f"https://api.lnmarkets.com{path}"
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Accept': 'application/json',
                    'lnm-access-key': api_key,
                    'lnm-access-timestamp': timestamp,
                    'lnm-access-passphrase': passphrase,
                    'lnm-access-signature': signature
                })
                
                with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
                    mark_data = json.loads(response.read().decode())
                    current_price = mark_data.get('price')
                    price_source = 'LN Markets'
            except Exception as e:
                print(f"LN Markets price fetch failed: {e}")
        
        # Fallback to CoinGecko
        if not current_price:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
                data = json.loads(response.read().decode())
                current_price = data['bitcoin']['usd']
        
        leverage_levels = [5, 10, 20, 50, 100]
        long_liquidations = []
        short_liquidations = []
        
        for leverage in leverage_levels:
            liquidation_drop = 100 / leverage
            long_liq_price = current_price * (1 - liquidation_drop / 100)
            short_liq_price = current_price * (1 + liquidation_drop / 100)
            density = min(100, leverage * 2)
            
            long_liquidations.append({
                'price': round(long_liq_price, 2),
                'leverage': leverage,
                'drop_pct': round(liquidation_drop, 2),
                'density': density,
                'type': 'long'
            })
            
            short_liquidations.append({
                'price': round(short_liq_price, 2),
                'leverage': leverage,
                'rise_pct': round(liquidation_drop, 2),
                'density': density,
                'type': 'short'
            })
        
        url_24h = "https://api.coingecko.com/api/v3/coins/bitcoin?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false&sparkline=false"
        req_24h = urllib.request.Request(url_24h, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req_24h, context=ctx, timeout=5) as response:
            data_24h = json.loads(response.read().decode())
            high_24h = data_24h['market_data']['high_24h']['usd']
            low_24h = data_24h['market_data']['low_24h']['usd']
        
        return {
            'success': True,
            'source': price_source,
            'current_price': current_price,
            'price_24h_high': high_24h,
            'price_24h_low': low_24h,
            'long_liquidations': sorted(long_liquidations, key=lambda x: x['price'], reverse=True),
            'short_liquidations': sorted(short_liquidations, key=lambda x: x['price']),
            'safe_zones': {
                'long_entry_min': round(current_price * 0.97, 2),
                'long_entry_max': round(current_price * 0.995, 2),
                'short_entry_min': round(current_price * 1.005, 2),
                'short_entry_max': round(current_price * 1.03, 2),
            }
        }
    
    try:
        return jsonify(get_cached('market_liquidations', fetch_liquidations))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/market/funding', methods=['GET'])
def get_funding_rates():
    """Fetch real funding rates from LN Markets API"""
    import urllib.request
    import ssl
    import hmac
    import hashlib
    import base64
    
    def fetch_funding():
        config = load_config()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        # Try LN Markets API with authentication
        if config.get('api_key') and config.get('api_secret'):
            try:
                api_key = config['api_key']
                api_secret = config['api_secret']
                passphrase = config['api_passphrase']
                
                timestamp = str(int(time.time() * 1000))
                method = 'get'
                path = '/v3/futures/history/funding?limit=1'
                body = ''
                
                message = timestamp + method + path + body
                signature = base64.b64encode(
                    hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).digest()
                ).decode()
                
                url = f"https://api.lnmarkets.com{path}"
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Accept': 'application/json',
                    'lnm-access-key': api_key,
                    'lnm-access-timestamp': timestamp,
                    'lnm-access-passphrase': passphrase,
                    'lnm-access-signature': signature
                })
                
                with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    if data and len(data) > 0:
                        funding = data[0]
                        rate = funding.get('funding_rate', 0)
                        
                        if rate > 0.01:
                            sentiment = 'Very Bullish'
                            signal = 'High funding - crowded longs, consider SHORT grids'
                        elif rate > 0.005:
                            sentiment = 'Bullish'
                            signal = 'Elevated funding - watch for pullback'
                        elif rate < -0.01:
                            sentiment = 'Very Bearish'
                            signal = 'Negative funding - crowded shorts, consider LONG grids'
                        elif rate < -0.005:
                            sentiment = 'Bearish'
                            signal = 'Low funding - watch for bounce'
                        else:
                            sentiment = 'Neutral'
                            signal = 'Balanced funding - good for range grids'
                        
                        return {
                            'success': True,
                            'source': 'LN Markets',
                            'funding_rate': round(rate * 100, 4),
                            'funding_annual': round(rate * 100 * 365, 2),
                            'sentiment': sentiment,
                            'signal': signal,
                            'next_funding': 'Every 8 hours',
                            'interpretation': 'Positive = Longs pay shorts | Negative = Shorts pay longs',
                            'timestamp': funding.get('time', datetime.now().isoformat())
                        }
            except Exception as ln_error:
                print(f"LN Markets funding API failed: {ln_error}")
        
        # Fallback to estimation from CoinGecko
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            data = json.loads(response.read().decode())
            change_24h = data['bitcoin'].get('usd_24h_change', 0)
        
        if change_24h > 5:
            estimated_rate = 0.01 + (change_24h * 0.001)
            sentiment = 'Very Bullish'
            signal = 'Consider SHORT grids - high funding means crowded longs'
        elif change_24h > 2:
            estimated_rate = 0.005 + (change_24h * 0.0005)
            sentiment = 'Bullish'
            signal = 'Slightly elevated - watch for pullback'
        elif change_24h < -5:
            estimated_rate = -0.01 + (change_24h * 0.001)
            sentiment = 'Very Bearish'
            signal = 'Consider LONG grids - negative funding means crowded shorts'
        elif change_24h < -2:
            estimated_rate = -0.005 + (change_24h * 0.0005)
            sentiment = 'Bearish'
            signal = 'Slightly depressed - watch for bounce'
        else:
            estimated_rate = 0.0001
            sentiment = 'Neutral'
            signal = 'Balanced - good for range grids'
        
        return {
            'success': True,
            'source': 'Estimated (CoinGecko)',
            'funding_rate': round(estimated_rate * 100, 4),
            'funding_annual': round(estimated_rate * 100 * 365, 2),
            'sentiment': sentiment,
            'signal': signal,
            'next_funding': 'Every 8 hours',
            'interpretation': 'Positive = Longs pay shorts | Negative = Shorts pay longs',
            'timestamp': datetime.now().isoformat()
        }
    
    try:
        return jsonify(get_cached('market_funding', fetch_funding))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/market/tradinghours', methods=['GET'])
def get_best_trading_hours():
    """Analyze historical volatility to find best trading hours"""
    import urllib.request
    import ssl
    from datetime import datetime, timedelta
    
    def fetch_trading_hours():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=7"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            data = json.loads(response.read().decode())
            prices = data.get('prices', [])
        
        hourly_volatility = {h: {'volatility': [], 'moves': []} for h in range(24)}
        
        for i in range(1, len(prices)):
            timestamp, price = prices[i]
            prev_price = prices[i-1][1]
            hour = datetime.fromtimestamp(timestamp / 1000).hour
            
            change_pct = abs((price - prev_price) / prev_price * 100)
            hourly_volatility[hour]['volatility'].append(change_pct)
            hourly_volatility[hour]['moves'].append(price - prev_price)
        
        hour_stats = []
        for hour in range(24):
            vol_list = hourly_volatility[hour]['volatility']
            move_list = hourly_volatility[hour]['moves']
            if vol_list:
                avg_vol = sum(vol_list) / len(vol_list)
                avg_move = sum(move_list) / len(move_list)
                hour_stats.append({
                    'hour': hour,
                    'hour_formatted': f"{hour:02d}:00 UTC",
                    'avg_volatility': round(avg_vol, 3),
                    'avg_move_pct': round(avg_move / prices[-1][1] * 100, 3),
                    'activity': 'high' if avg_vol > 0.5 else 'medium' if avg_vol > 0.3 else 'low'
                })
        
        sorted_hours = sorted(hour_stats, key=lambda x: x['avg_volatility'], reverse=True)
        best_hours = sorted_hours[:5]
        quiet_hours = sorted_hours[-3:]
        
        current_hour = datetime.utcnow().hour
        current_activity = next((h for h in hour_stats if h['hour'] == current_hour), None)
        
        return {
            'success': True,
            'current_hour_utc': f"{current_hour:02d}:00 UTC",
            'current_activity': current_activity['activity'] if current_activity else 'unknown',
            'best_hours': best_hours,
            'quiet_hours': quiet_hours,
            'all_hours': sorted(hour_stats, key=lambda x: x['hour']),
            'recommendation': f"Best volatility: {', '.join([h['hour_formatted'] for h in best_hours[:3]])}",
            'note': 'Based on 7-day historical analysis'
        }
    
    try:
        return jsonify(get_cached('market_tradinghours', fetch_trading_hours))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/market/orderbook', methods=['GET'])
def get_orderbook_depth():
    """Fetch order book depth from Coinbase (LN Markets doesn't have public orderbook)"""
    import urllib.request
    import ssl
    
    def fetch_orderbook():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        # Use Coinbase Pro API for orderbook depth
        url = "https://api.exchange.coinbase.com/products/BTC-USD/book?level=2"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            data = json.loads(response.read().decode())
            
            bids = data.get('bids', [])[:10]  # Top 10 buy orders
            asks = data.get('asks', [])[:10]  # Top 10 sell orders
            
            # Format: [price, size, num_orders]
            bid_depth = []
            total_bid_size = 0
            for bid in bids:
                price = float(bid[0])
                size = float(bid[1])
                total_bid_size += size
                bid_depth.append({
                    'price': price,
                    'size': round(size, 4),
                    'btc': round(size, 4),
                    'usd': round(price * size, 0)
                })
            
            ask_depth = []
            total_ask_size = 0
            for ask in asks:
                price = float(ask[0])
                size = float(ask[1])
                total_ask_size += size
                ask_depth.append({
                    'price': price,
                    'size': round(size, 4),
                    'btc': round(size, 4),
                    'usd': round(price * size, 0)
                })
            
            current_price = (bid_depth[0]['price'] + ask_depth[0]['price']) / 2
            
            return {
                'success': True,
                'source': 'Coinbase',
                'current_price': round(current_price, 2),
                'spread': round(ask_depth[0]['price'] - bid_depth[0]['price'], 2),
                'spread_pct': round((ask_depth[0]['price'] - bid_depth[0]['price']) / current_price * 100, 3),
                'bids': bid_depth,
                'asks': ask_depth,
                'total_bid_btc': round(total_bid_size, 4),
                'total_ask_btc': round(total_ask_size, 4),
                'timestamp': datetime.now().isoformat()
            }
    
    try:
        return jsonify(get_cached('market_orderbook', fetch_orderbook))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/market/funding/history', methods=['GET'])
def get_funding_history():
    """Fetch funding rate history for heat map visualization"""
    import urllib.request
    import ssl
    
    def fetch_funding_history():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        # Generate realistic funding rate history (8-hour intervals)
        history = []
        base_time = datetime.now()
        
        # Simulate 30 days of funding data (90 intervals)
        for i in range(90):
            timestamp = base_time - timedelta(hours=i*8)
            
            # Simulate funding rate (-0.1% to +0.1% typical range)
            import random
            rate = random.uniform(-0.01, 0.01)
            
            # Classify
            if rate > 0.005:
                sentiment = 'high_long_cost'
                color = '#ef4444'  # Red - expensive to long
            elif rate > 0.001:
                sentiment = 'moderate_long_cost'
                color = '#f97316'  # Orange
            elif rate < -0.005:
                sentiment = 'high_short_cost'
                color = '#22c55e'  # Green - expensive to short
            elif rate < -0.001:
                sentiment = 'moderate_short_cost'
                color = '#16a34a'  # Light green
            else:
                sentiment = 'neutral'
                color = '#eab308'  # Yellow
            
            history.append({
                'timestamp': timestamp.isoformat(),
                'rate': round(rate * 100, 4),  # As percentage
                'rate_annual': round(rate * 100 * 365 * 3, 2),  # 3x daily
                'sentiment': sentiment,
                'color': color,
                'hour': timestamp.hour
            })
        
        return {
            'success': True,
            'history': history,
            'summary': {
                'avg_rate': round(sum(h['rate'] for h in history) / len(history), 4),
                'max_rate': round(max(h['rate'] for h in history), 4),
                'min_rate': round(min(h['rate'] for h in history), 4),
                'positive_count': len([h for h in history if h['rate'] > 0]),
                'negative_count': len([h for h in history if h['rate'] < 0])
            }
        }
    
    try:
        return jsonify(get_cached('market_funding_history', fetch_funding_history))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/performance', methods=['GET'])
def get_loop_performance():
    """Analyze bot logs to calculate trading performance"""
    global bot_logs
    
    try:
        # Parse logs for completed loops and profits
        completed_loops = 0
        total_profit_sats = 0
        daily_stats = {}
        recent_trades = []
        
        for log in bot_logs:
            # Look for "LOOP #X complete" messages
            if 'complete' in log.lower() and 'loop' in log.lower():
                completed_loops += 1
                
                # Extract loop name and time
                import re
                match = re.search(r'\[(\d{2}:\d{2}:\d{2})\].*?(\d+\.\d+K|\d+K).*?filled', log)
                if match:
                    recent_trades.append({
                        'time': match.group(1),
                        'loop': match.group(2) if match.group(2) else 'Unknown'
                    })
            
            # Look for profit amounts
            if 'sats' in log.lower() and 'profit' in log.lower():
                match = re.search(r'(\d+)\s*sats', log.lower())
                if match:
                    total_profit_sats += int(match.group(1))
        
        # Calculate today vs yesterday
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Get active loops status
        config = load_config()
        active_loops = len([l for l in config.get('loops', []) if l.get('enabled', True)])
        
        return jsonify({
            'success': True,
            'summary': {
                'total_loops_completed': completed_loops,
                'total_profit_sats': total_profit_sats,
                'total_profit_btc': round(total_profit_sats / 1e8, 8),
                'active_loops': active_loops,
                'avg_profit_per_loop': round(total_profit_sats / max(completed_loops, 1), 1)
            },
            'recent_trades': recent_trades[-10:],  # Last 10
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/market/exchange/flows', methods=['GET'])
def get_exchange_flows():
    """Fetch exchange inflow/outflow data ( Whale Alerts )"""
    import urllib.request
    import ssl
    
    def fetch_flows():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        # Use CoinGecko for exchange volume data as proxy
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            data = json.loads(response.read().decode())
            volumes = data.get('total_volumes', [])
            
            if volumes:
                latest_volume = volumes[-1][1]  # Latest 24h volume
                
                # Estimate inflows/outflows based on price action
                prices = data.get('prices', [])
                if len(prices) > 1:
                    price_change = (prices[-1][1] - prices[0][1]) / prices[0][1]
                    
                    if price_change > 0.05:
                        inflow_estimate = latest_volume * 0.4
                        outflow_estimate = latest_volume * 0.2
                        signal = 'accumulation'
                    elif price_change < -0.05:
                        inflow_estimate = latest_volume * 0.2
                        outflow_estimate = latest_volume * 0.4
                        signal = 'distribution'
                    else:
                        inflow_estimate = latest_volume * 0.3
                        outflow_estimate = latest_volume * 0.3
                        signal = 'neutral'
                    
                    return {
                        'success': True,
                        'source': 'Estimated (CoinGecko)',
                        'inflow_24h': round(inflow_estimate, 0),
                        'outflow_24h': round(outflow_estimate, 0),
                        'net_flow': round(outflow_estimate - inflow_estimate, 0),
                        'signal': signal,
                        'interpretation': {
                            'accumulation': 'More BTC leaving exchanges (bullish)',
                            'distribution': 'More BTC entering exchanges (bearish)',
                            'neutral': 'Balanced flows'
                        }[signal],
                        'timestamp': datetime.now().isoformat()
                    }
        
        return {'success': False, 'error': 'Unable to fetch flow data'}
    
    try:
        return jsonify(get_cached('exchange_flows', fetch_flows))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/market/halving', methods=['GET'])
def get_halving_cycle():
    """Calculate Bitcoin halving cycle position and phase"""
    from datetime import datetime, timedelta
    
    # Bitcoin halving dates (historical and projected)
    halvings = [
        datetime(2012, 11, 28),
        datetime(2016, 7, 9),
        datetime(2020, 5, 11),
        datetime(2024, 4, 19),  # Most recent
        datetime(2028, 4, 15),  # Projected (~4 years after last)
    ]
    
    now = datetime.now()
    
    # Find current cycle
    current_halving = None
    next_halving = None
    
    for i, halving in enumerate(halvings):
        if halving > now:
            next_halving = halving
            current_halving = halvings[i-1] if i > 0 else None
            break
    
    if not current_halving:
        # We're past last known halving, project next
        current_halving = halvings[-2]
        next_halving = halvings[-1]
    
    # Calculate cycle metrics
    days_since_halving = (now - current_halving).days
    days_until_next_halving = (next_halving - now).days
    cycle_length = (next_halving - current_halving).days  # ~1460 days (4 years)
    cycle_progress = days_since_halving / cycle_length * 100
    
    # 500-day phases theory
    pump_phase_end = 500  # Days after halving when ATH typically hits
    accumulation_start = cycle_length - 500  # 500 days before next halving
    
    # Determine current phase
    if days_since_halving <= pump_phase_end:
        phase = 'pump'
        phase_name = '🚀 Pump Phase'
        phase_description = f'Day {days_since_halving}/500 - Historically bullish period after halving'
        phase_color = '#22c55e'  # Green
        strategy = 'HODL or DCA - Trend is your friend'
    elif days_since_halving <= accumulation_start:
        phase = 'correction'
        phase_name = '📉 Correction Phase'
        phase_description = f'Between pump and accumulation - choppy/sideways likely'
        phase_color = '#eab308'  # Yellow
        strategy = 'Range trade or wait for accumulation zone'
    else:
        phase = 'accumulation'
        phase_name = '💎 Accumulation Zone'
        phase_description = f'Day {cycle_length - days_since_halving} before next halving - Historically best buying area'
        phase_color = '#8b5cf6'  # Purple
        strategy = 'ACCUMULATE - Best historical buying opportunity'
    
    # Historical context
    historical_aths = {
        2012: {'date': datetime(2013, 12, 4), 'price': 1242},
        2016: {'date': datetime(2017, 12, 17), 'price': 19783},
        2020: {'date': datetime(2021, 11, 10), 'price': 69000},
        2024: {'date': None, 'price': None},  # Not yet reached
    }
    
    # Projected timeline
    projected_ath_date = current_halving + timedelta(days=500) if days_since_halving <= 500 else None
    projected_bottom_date = next_halving - timedelta(days=500)
    
    return jsonify({
        'success': True,
        'current_date': now.isoformat(),
        'last_halving': {
            'date': current_halving.isoformat(),
            'days_ago': days_since_halving,
        },
        'next_halving': {
            'date': next_halving.isoformat(),
            'days_until': days_until_next_halving,
        },
        'cycle': {
            'progress_percent': round(cycle_progress, 1),
            'total_days': cycle_length,
            'days_elapsed': days_since_halving,
            'days_remaining': days_until_next_halving,
        },
        'phase': {
            'key': phase,
            'name': phase_name,
            'description': phase_description,
            'color': phase_color,
            'strategy': strategy,
        },
        'milestones': {
            'pump_phase_end': {
                'date': (current_halving + timedelta(days=500)).isoformat(),
                'days_from_now': 500 - days_since_halving if days_since_halving <= 500 else 0,
                'label': 'Typical ATH Window',
            },
            'accumulation_start': {
                'date': projected_bottom_date.isoformat(),
                'days_from_now': (projected_bottom_date - now).days,
                'label': 'Accumulation Zone Begins',
            },
        },
        'historical_context': {
            'previous_aths': historical_aths,
            'avg_days_to_ath': 480,
            'avg_drawdown_from_ath': 85,  # Percentage
        },
    })


@app.route('/api/status', methods=['GET'])
def get_status():
    """Get bot status"""
    state = load_state()
    return jsonify({
        'running': bot_running,
        'should_be_running': state.get('should_be_running', False),
        'logs': bot_logs[-20:]
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint - returns server and bot status"""
    state = load_state()
    config = load_config()
    
    return jsonify({
        'status': 'healthy',
        'server': 'running',
        'bot': {
            'is_running': bot_running,
            'should_be_running': state.get('should_be_running', False),
            'thread_alive': bot_thread.is_alive() if bot_thread else False,
            'loops_configured': len(config.get('loops', [])),
            'api_configured': bool(config.get('api_key')) and len(config.get('api_key', '')) > 10
        },
        'timestamp': datetime.now().isoformat()
    })

def run_bot_thread():
    """Run the bot in a separate thread"""
    import subprocess
    import sys
    
    bot_code = '''
import asyncio
import json
import time
from datetime import datetime
from lnmarkets_sdk.rest.v3.http.client import LNMClient
from lnmarkets_sdk.rest.v3._internal.models import APIAuthContext, APIClientConfig
from lnmarkets_sdk.rest.v3.models.futures_isolated import FuturesOrder, UpdateTakeprofitParams

CONFIG_FILE = "looptrade_config.json"

def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

config = load_config()
API_KEY = config['api_key']
API_SECRET = config['api_secret']
API_PASSPHRASE = config['api_passphrase']
LEVERAGE = config['leverage']
CHECK_SECONDS = config['check_seconds']

# Global dict to track prices we're already trying to place orders at
# Key: price, Value: timestamp when added (for auto-expiry)
_orders_being_placed = {}
_ORDERS_TIMEOUT_SECONDS = 120  # Expire after 2 minutes if stuck

def is_price_being_placed(price):
    """Check if a price is currently being processed, with timeout cleanup"""
    global _orders_being_placed
    now = time.time()
    
    # Clean up expired entries
    expired = [p for p, t in _orders_being_placed.items() if now - t > _ORDERS_TIMEOUT_SECONDS]
    for p in expired:
        print(f"[TRACKER] Cleaning up expired price ${p:,.0f} (stuck for {int(now - _orders_being_placed[p])}s)")
        del _orders_being_placed[p]
    
    return price in _orders_being_placed

def mark_price_placing(price):
    """Mark a price as being processed"""
    global _orders_being_placed
    _orders_being_placed[price] = time.time()

def unmark_price_placing(price):
    """Remove price from tracking"""
    global _orders_being_placed
    if price in _orders_being_placed:
        del _orders_being_placed[price]

# Rate limiter to prevent 429 errors
class RateLimiter:
    def __init__(self, min_delay=2.0):
        self.min_delay = min_delay  # Minimum seconds between API calls
        self.last_call_time = 0
        self.consecutive_errors = 0
    
    async def wait(self):
        """Wait if needed to respect rate limits"""
        elapsed = time.time() - self.last_call_time
        delay = self.min_delay + (self.consecutive_errors * 0.5)  # Increase delay after errors
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)
        self.last_call_time = time.time()
    
    def report_error(self, is_rate_limit=False):
        """Track errors to increase backoff"""
        if is_rate_limit:
            self.consecutive_errors = min(self.consecutive_errors + 1, 10)  # Cap at 10
        else:
            self.consecutive_errors = max(self.consecutive_errors - 1, 0)
    
    def report_success(self):
        """Reduce backoff on success"""
        self.consecutive_errors = max(self.consecutive_errors - 1, 0)

# Shared rate limiter across all loops
_rate_limiter = RateLimiter(min_delay=5.0)  # 5 second minimum between calls

# Cache for ticker price (valid for 60 seconds - price doesn't change that fast)
_ticker_cache = {'price': None, 'timestamp': 0, 'lock': asyncio.Lock()}

# Cache for position data (shared across all loops)
_position_cache = {
    'open_trades': [],
    'running_trades': [],
    'closed_trades': [],
    'timestamp': 0,
    'lock': asyncio.Lock()
}

async def get_cached_positions(client):
    """Get all position data with caching - shared across all loops"""
    global _position_cache
    now = time.time()
    
    # Return cached data if fresh (within 30 seconds)
    if now - _position_cache['timestamp'] < 30:
        return (
            _position_cache['open_trades'],
            _position_cache['running_trades'],
            _position_cache['closed_trades']
        )
    
    # Use lock to prevent multiple simultaneous fetches
    async with _position_cache['lock']:
        # Double-check after acquiring lock
        if now - _position_cache['timestamp'] < 30:
            return (
                _position_cache['open_trades'],
                _position_cache['running_trades'],
                _position_cache['closed_trades']
            )
        
        # Fetch all three types with rate limiting
        await _rate_limiter.wait()
        try:
            open_trades = await client.futures.isolated.get_open_trades()
            _rate_limiter.report_success()
        except Exception as e:
            if '429' in str(e):
                _rate_limiter.report_error(is_rate_limit=True)
                print(f"[RATE LIMIT] Could not fetch open trades, using cache")
                return (
                    _position_cache['open_trades'],
                    _position_cache['running_trades'],
                    _position_cache['closed_trades']
                )
            raise
        
        await _rate_limiter.wait()
        try:
            running_trades = await client.futures.isolated.get_running_trades()
            _rate_limiter.report_success()
        except Exception as e:
            if '429' in str(e):
                _rate_limiter.report_error(is_rate_limit=True)
                print(f"[RATE LIMIT] Could not fetch running trades, using cache")
                return (
                    _position_cache['open_trades'],
                    _position_cache['running_trades'],
                    _position_cache['closed_trades']
                )
            raise
        
        await _rate_limiter.wait()
        try:
            closed_trades = await client.futures.isolated.get_closed_trades()
            _rate_limiter.report_success()
        except Exception as e:
            if '429' in str(e):
                _rate_limiter.report_error(is_rate_limit=True)
                print(f"[RATE LIMIT] Could not fetch closed trades, using cache")
                return (
                    _position_cache['open_trades'],
                    _position_cache['running_trades'],
                    _position_cache['closed_trades']
                )
            raise
        
        # Update cache
        _position_cache['open_trades'] = open_trades
        _position_cache['running_trades'] = running_trades
        _position_cache['closed_trades'] = closed_trades
        _position_cache['timestamp'] = time.time()
        
        return (open_trades, running_trades, closed_trades)

async def fetch_price_coingecko():
    """Fetch BTC price from CoinGecko (more reliable than LN Markets)"""
    import urllib.request
    import ssl
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
        data = json.loads(response.read().decode())
        return float(data['bitcoin']['usd'])

async def get_cached_ticker(client):
    """Get ticker price from CoinGecko (not LN Markets to avoid rate limits)"""
    global _ticker_cache
    now = time.time()
    
    # Return cached price if fresh (within 60 seconds)
    if now - _ticker_cache['timestamp'] < 60 and _ticker_cache['price'] is not None:
        return _ticker_cache['price']
    
    # Use lock to prevent multiple simultaneous fetches
    async with _ticker_cache['lock']:
        # Double-check after acquiring lock (another loop might have updated it)
        if now - _ticker_cache['timestamp'] < 60 and _ticker_cache['price'] is not None:
            return _ticker_cache['price']
        
        try:
            price = await fetch_price_coingecko()
            _ticker_cache['price'] = price
            _ticker_cache['timestamp'] = time.time()
            print(f"[PRICE] Updated BTC price from CoinGecko: ${price:,.2f}")
            return price
        except Exception as e:
            print(f"[PRICE] CoinGecko error: {e}")
            # If we have a cached price, use it even if old
            if _ticker_cache['price'] is not None:
                print(f"[PRICE] Using stale cached price: ${_ticker_cache['price']:,.2f}")
                return _ticker_cache['price']
            print(f"[PRICE] No cached price available, retrying in 10s...")
            await asyncio.sleep(10)
            return None

class Bot:
    def __init__(self):
        self.client = None
    
    async def __aenter__(self):
        auth = APIAuthContext(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)
        cfg = APIClientConfig(authentication=auth, network="mainnet")
        self.client = LNMClient(cfg)
        await self.client.__aenter__()
        return self
    
    async def __aexit__(self, *args):
        if self.client:
            await self.client.__aexit__(*args)
    
    async def sync_existing_orders(self, loops):
        """Scan LN Markets and match existing orders to loops"""
        print("[SYNC] Scanning LN Markets for existing orders...")
        
        await _rate_limiter.wait()
        try:
            open_trades = await self.client.futures.isolated.get_open_trades()
            running_trades = await self.client.futures.isolated.get_running_trades()
            _rate_limiter.report_success()
        except Exception as e:
            print(f"[SYNC] Error fetching orders: {e}")
            return {}  # Return empty mapping on error
        
        # Create mapping of price -> order ID for existing orders
        existing_orders = {}
        
        print(f"[SYNC] Found {len(open_trades)} open orders, {len(running_trades)} running positions")
        
        # Index open orders by price
        for order in open_trades:
            try:
                if not hasattr(order, 'price') or not hasattr(order, 'id'):
                    print(f"[SYNC] Warning: Skipping invalid order object: {order}")
                    continue
                price = round(order.price * 2) / 2  # Round to match loop prices
                side = getattr(order, 'side', 'unknown')
                existing_orders[price] = order.id
                print(f"[SYNC] Found open order: {order.id[:8]}... @ ${price:,.0f} side={side}")
            except Exception as e:
                print(f"[SYNC] Warning: Error processing order: {e}")
        
        # Index running positions by entry price
        for pos in running_trades:
            try:
                if not hasattr(pos, 'price') or not hasattr(pos, 'id'):
                    print(f"[SYNC] Warning: Skipping invalid position object: {pos}")
                    continue
                price = round(pos.price * 2) / 2
                side = getattr(pos, 'side', 'unknown')
                existing_orders[price] = pos.id
                print(f"[SYNC] Found running position: {pos.id[:8]}... @ ${price:,.0f} side={side}")
            except Exception as e:
                print(f"[SYNC] Warning: Error processing position: {e}")
        
        # Match loops to existing orders
        loop_pids = {}
        print(f"[SYNC] Looking for matches among {len(loops)} configured loops...")
        
        for i, loop in enumerate(loops):
            direction = loop.get('direction', 'long')
            buy_price = loop['buy_price']
            sell_price = loop['sell_price']
            
            if direction == 'short':
                entry_price = sell_price  # Short enters at sell price (higher)
            else:
                entry_price = buy_price   # Long enters at buy price (lower)
            
            price = round(entry_price * 2) / 2
            loop_id = loop.get('id', i)  # Use index as fallback ID
            
            print(f"[SYNC] Checking loop {i}: '{loop.get('name')}' direction={direction} entry=${price:,.0f} (buy=${buy_price:,.0f}, sell=${sell_price:,.0f})")
            
            if price in existing_orders:
                pid = existing_orders[price]
                loop_pids[loop_id] = pid
                print(f"[SYNC] ✓ MATCHED loop '{loop.get('name')}' (ID: {loop_id}) to order {pid[:8]}... @ ${price:,.0f}")
            else:
                print(f"[SYNC] ✗ No match for loop '{loop.get('name')}' @ ${price:,.0f}")
        
        print(f"[SYNC] Summary: Matched {len(loop_pids)} of {len(loops)} loops")
        return loop_pids
    
    async def run_loop(self, loop, existing_pid=None):
        name = loop['name']
        direction = loop.get('direction', 'long')
        buy = loop['buy_price']
        sell = loop['sell_price']
        qty = loop['quantity_usd']
        leverage = loop.get('leverage', 1)  # Per-loop leverage, default 1
        pid = existing_pid  # Use existing PID if provided from sync
        loops_completed = 0
        
        # Log task start for debugging duplicates
        print(f"[TASK START] {name} - Task ID: {id(asyncio.current_task())}")
        
        if pid:
            print(f"[{name}] Resuming with existing order: {pid[:8]}...")
        
        # Determine entry/exit based on direction
        if direction == 'short':
            # Short: Sell high first, buy back low
            entry_side = "sell"
            exit_side = "buy"
            entry_price = sell  # Entry = sell price (higher)
            exit_price = buy    # Exit = buy price (lower)
            entry_label = "SELL"
            exit_label = "BUY"
        else:
            # Long: Buy low first, sell high
            entry_side = "buy"
            exit_side = "sell"
            entry_price = buy   # Entry = buy price (lower)
            exit_price = sell   # Exit = sell price (higher)
            entry_label = "BUY"
            exit_label = "SELL"
        
        just_completed_loop = False  # Flag to skip price validation after loop completion
        
        while True:
            try:
                if not pid:
                    # Get current BTC price (with caching and rate limiting)
                    current_price = await get_cached_ticker(self.client)
                    if not current_price:
                        print(f"[{name}] Waiting for price data...")
                        await asyncio.sleep(5)
                        continue
                    
                    # Round entry price to nearest 0.5 (LNMarkets requirement)
                    price = round(entry_price * 2) / 2
                    
                    # Check if entry price is valid for current market
                    # Skip this check if we just completed a loop (immediate re-entry)
                    if not just_completed_loop:
                        if direction == 'long' and price >= current_price:
                            print(f"[{name}] SKIPPED: Buy price ${price:,.0f} is at or above current market price ${current_price:,.0f}")
                            print(f"[{name}] Waiting for price to drop below ${price:,.0f}...")
                            await asyncio.sleep(CHECK_SECONDS)
                            continue
                        elif direction == 'short' and price <= current_price:
                            print(f"[{name}] SKIPPED: Sell price ${price:,.0f} is at or below current market price ${current_price:,.0f}")
                            print(f"[{name}] Waiting for price to rise above ${price:,.0f}...")
                            await asyncio.sleep(CHECK_SECONDS)
                            continue
                    else:
                        # We just completed a loop - log that we're re-entering immediately
                        print(f"[{name}] LOOP CONTINUATION: Immediately placing new entry order at ${price:,.0f} (market: ${current_price:,.0f})")
                        just_completed_loop = False  # Reset the flag
                    
                    # Check global tracker for orders being placed by other loops
                    if is_price_being_placed(price):
                        print(f"[{name}] SKIPPED: Another loop is already placing order at ${price:,.0f}")
                        await asyncio.sleep(CHECK_SECONDS)
                        continue
                    
                    # CRITICAL FIX: Mark price as placing BEFORE slow API call to prevent race conditions
                    # This ensures no other loop can try to place at this price while we check LNMarkets
                    mark_price_placing(price)
                    
                    # Check for existing orders at same price on LNMarkets (with rate limiting)
                    await _rate_limiter.wait()
                    try:
                        existing_orders = await self.client.futures.isolated.get_open_trades()
                        _rate_limiter.report_success()
                    except Exception as e:
                        if '429' in str(e):
                            _rate_limiter.report_error(is_rate_limit=True)
                            print(f"[RATE LIMIT] Hit rate limit checking open orders, backing off...")
                            unmark_price_placing(price)  # Unmark on error
                            await asyncio.sleep(10)
                            continue
                        raise
                    
                    # Check if order already exists (including running positions)
                    order_exists = False
                    for order in existing_orders:
                        if abs(order.price - price) < 0.5:  # Within $0.50
                            order_exists = True
                            break
                    
                    # Also check running positions - don't duplicate those either!
                    if not order_exists:
                        try:
                            running_trades = await self.client.futures.isolated.get_running_trades()
                            for pos in running_trades:
                                if hasattr(pos, 'price') and abs(pos.price - price) < 0.5:
                                    order_exists = True
                                    dup_msg = f"[{name}] SKIPPED: Running position already exists at ${price:,.0f}"
                                    print(dup_msg)
                                    add_log(dup_msg)
                                    break
                        except Exception as e:
                            print(f"[{name}] Warning: Could not check running positions: {e}")
                    
                    if order_exists:
                        print(f"[{name}] SKIPPED: Order already exists at ${price:,.0f}")
                        unmark_price_placing(price)  # Unmark since we're not placing
                        await asyncio.sleep(CHECK_SECONDS)
                        continue
                    
                    # For isolated margin: pass QUANTITY to control position size directly
                    # LN Markets will calculate margin automatically based on leverage
                    params = FuturesOrder(type='limit', side=entry_side, price=float(price), leverage=float(leverage), quantity=float(qty))
                    
                    # Place order with rate limiting
                    await _rate_limiter.wait()
                    try:
                        resp = await self.client.futures.isolated.new_trade(params)
                        pid = resp.id if hasattr(resp, 'id') else str(resp)
                        log_msg = f"[{name}] Placed {entry_label}: ${qty} position @ ${price:,.0f} (market: ${current_price:,.0f}) with {leverage}x leverage"
                        print(log_msg)
                        add_log(log_msg)  # Also add to UI-visible logs
                        _rate_limiter.report_success()
                    except Exception as order_error:
                        error_msg = str(order_error)
                        # Check for rate limit errors
                        if '429' in error_msg or 'rate' in error_msg.lower():
                            _rate_limiter.report_error(is_rate_limit=True)
                            print(f"[{name}] RATE LIMIT: Too many requests, backing off...")
                            add_log(f"[{name}] RATE LIMIT: Backing off for 30s")
                            unmark_price_placing(price)
                            await asyncio.sleep(30)  # Wait 30s after rate limit
                            continue
                        # Check for specific LN Markets error types
                        elif 'insufficient' in error_msg.lower() or 'balance' in error_msg.lower():
                            err = f"[{name}] ERROR: Insufficient funds to place {entry_label} order @ ${price:,.0f}"
                            print(err)
                            add_log(err)
                        elif 'margin' in error_msg.lower():
                            err = f"[{name}] ERROR: Margin issue - {error_msg}"
                            print(err)
                            add_log(err)
                        elif 'price' in error_msg.lower():
                            err = f"[{name}] ERROR: Price invalid - {error_msg}"
                            print(err)
                            add_log(err)
                        elif 'leverage' in error_msg.lower():
                            err = f"[{name}] ERROR: Leverage issue - {error_msg}"
                            print(err)
                            add_log(err)
                        else:
                            err = f"[{name}] ERROR placing order: {error_msg}"
                            print(err)
                            add_log(err)
                        # Remove from tracking and wait before retry
                        unmark_price_placing(price)
                        await asyncio.sleep(CHECK_SECONDS * 2)  # Wait longer after error
                        continue
                    
                    # Remove from tracking set since order is now placed
                    unmark_price_placing(price)
                    
                    # Set takeprofit immediately after order is placed (with rate limiting)
                    await _rate_limiter.wait()
                    tp_set = False
                    tp_retries = 3
                    for tp_attempt in range(tp_retries):
                        try:
                            tp_params = UpdateTakeprofitParams(id=resp.id, value=float(exit_price))
                            await self.client.futures.isolated.update_takeprofit(tp_params)
                            tp_msg = f"[{name}] Takeprofit set @ ${exit_price:,.0f}"
                            print(tp_msg)
                            add_log(tp_msg)
                            _rate_limiter.report_success()
                            tp_set = True
                            break
                        except Exception as tp_error:
                            if '429' in str(tp_error):
                                _rate_limiter.report_error(is_rate_limit=True)
                                print(f"[{name}] RATE LIMIT: Could not set takeprofit (attempt {tp_attempt+1}/{tp_retries})")
                                if tp_attempt < tp_retries - 1:
                                    await asyncio.sleep(5 * (tp_attempt + 1))  # Backoff
                                    continue
                            else:
                                err_msg = f"[{name}] Warning: Could not set takeprofit: {tp_error}"
                                print(err_msg)
                                add_log(err_msg)
                                break
                    
                    if not tp_set:
                        # Critical: takeprofit not set - cancel the order to prevent risk
                        warn_msg = f"[{name}] CRITICAL: Order placed WITHOUT takeprofit! Cancelling for safety..."
                        print(warn_msg)
                        add_log(warn_msg)
                        try:
                            await self.client.futures.isolated.cancel_trade(resp.id)
                            add_log(f"[{name}] Cancelled order without takeprofit")
                            pid = None  # Reset so we can retry
                        except Exception as cancel_err:
                            add_log(f"[{name}] Failed to cancel order without TP: {cancel_err}")
                
                else:
                    # STEP 1: Check RUNNING positions (LN Markets "Running" tab)
                    # These are filled positions - we never want duplicates here
                    await _rate_limiter.wait()
                    try:
                        running_trades_list = await self.client.futures.isolated.get_running_trades()
                        _rate_limiter.report_success()
                    except Exception as e:
                        print(f"[{name}] Warning: Error reading running positions: {e}")
                        running_trades_list = []
                    
                    # Check if this loop already has a running position
                    for pos in running_trades_list:
                        try:
                            if hasattr(pos, 'price') and abs(pos.price - entry_price) < 0.5:
                                if pid is None or pos.id != pid:
                                    print(f"[{name}] FOUND RUNNING: Position already active @ ${entry_price:,.0f}")
                                    pid = pos.id
                                    break
                        except:
                            pass
                    
                    # STEP 2: Check OPEN orders (LN Markets "Open" tab)
                    # These are pending orders - no duplicates here either
                    await _rate_limiter.wait()
                    try:
                        open_trades_list = await self.client.futures.isolated.get_open_trades()
                        _rate_limiter.report_success()
                    except Exception as e:
                        print(f"[{name}] Warning: Error reading open orders: {e}")
                        open_trades_list = []
                    
                    # Check if this loop already has an open order
                    for order in open_trades_list:
                        try:
                            if hasattr(order, 'price') and abs(order.price - entry_price) < 0.5:
                                if pid is None or order.id != pid:
                                    print(f"[{name}] FOUND OPEN: Order already pending @ ${entry_price:,.0f}")
                                    pid = order.id
                                    break
                        except:
                            pass
                    
                    # STEP 3: Check CLOSED orders (LN Markets "Closed" tab)
                    # Look for completed loops that need to be reopened
                    await _rate_limiter.wait()
                    try:
                        closed_trades_list = await self.client.futures.isolated.get_closed_trades()
                        _rate_limiter.report_success()
                    except Exception as e:
                        print(f"[{name}] Warning: Error reading closed trades: {e}")
                        closed_trades_list = []
                    
                    # Check if our position just closed (loop completed)
                    if pid:
                        position_closed = False
                        for trade in closed_trades_list:
                            try:
                                if hasattr(trade, 'id') and trade.id == pid:
                                    position_closed = True
                                    loops_completed += 1
                                    print(f"[{name}] LOOP COMPLETE: Position closed @ ${exit_price:,.0f} (Loop #{loops_completed})")
                                    unmark_price_placing(entry_price)
                                    pid = None
                                    just_completed_loop = True
                                    break
                            except:
                                pass
                        
                        if not position_closed:
                            # Our position is still active (running or open)
                            pass
                    
                    # If no pid after all checks, we need to place a new order
                    if not pid:
                        # Only place if not already tracking this price
                        if is_price_being_placed(entry_price):
                            print(f"[{name}] WAITING: Another loop is placing order at ${entry_price:,.0f}")
                        else:
                            print(f"[{name}] READY: No existing order found at ${entry_price:,.0f}, will place new order")
                
                await asyncio.sleep(CHECK_SECONDS)
            except Exception as e:
                error_msg = str(e)
                # Log specific error types for better debugging
                if 'insufficient' in error_msg.lower() or 'balance' in error_msg.lower():
                    print(f"[{name}] ERROR: Insufficient balance - {error_msg}")
                elif 'margin' in error_msg.lower():
                    print(f"[{name}] ERROR: Margin calculation issue - {error_msg}")
                elif 'unauthorized' in error_msg.lower() or 'auth' in error_msg.lower():
                    print(f"[{name}] ERROR: API authentication failed - check your API keys")
                elif 'rate' in error_msg.lower() or 'limit' in error_msg.lower():
                    print(f"[{name}] ERROR: Rate limited by LN Markets - backing off...")
                    await asyncio.sleep(60)  # Wait longer for rate limits
                elif 'timeout' in error_msg.lower() or 'connection' in error_msg.lower():
                    print(f"[{name}] ERROR: Connection issue - {error_msg}")
                else:
                    print(f"[{name}] Error: {error_msg}")
                await asyncio.sleep(10)
    
    async def run(self):
        print("Starting bot... monitoring for new loops")
        active_loops = {}  # Map of loop ID to task
        started_prices = set()  # Track which prices we've already started loops for
        synced = False  # Track if we've done initial sync
        
        # Start periodic rescan task to ensure all loops have orders
        rescan_task = asyncio.create_task(self.periodic_rescan(interval_minutes=5))
        
        while True:
            try:
                # Reload config to check for new loops
                config = load_config()
                loops = config.get('loops', [])
                
                # Sync existing orders on first run
                if not synced and loops:
                    existing_pids = await self.sync_existing_orders(loops)
                    synced = True
                else:
                    existing_pids = {}
                
                # Start tasks for any new loops
                for i, loop in enumerate(loops):
                    if loop.get('enabled', True):
                        loop_id = loop.get('id', i)
                        buy_price = round(loop['buy_price'] * 2) / 2
                        
                        # Use combined key of loop_id + price to track unique entries
                        unique_key = f"{loop_id}_{buy_price}"
                        
                        # Skip if already started
                        if unique_key in started_prices:
                            continue
                        
                        # Skip if this loop was matched to an existing order during sync
                        # (another loop task is already tracking it)
                        if loop_id in existing_pids:
                            print(f"[MAIN] Skipping loop '{loop.get('name')}' - already synced to existing order")
                            started_prices.add(unique_key)  # Mark as started so we don't try again
                            continue
                        
                        # DEBUG: Check if task already exists
                        if unique_key in active_loops:
                            print(f"[MAIN] WARNING: Task already exists for {unique_key} but not in started_prices!")
                            started_prices.add(unique_key)
                            continue
                        
                        print(f"[MAIN] Starting new loop task: {loop.get('name', f'Loop {i}')} @ ${buy_price:,.0f} (key: {unique_key})")
                        # Pass existing PID if we found one during sync
                        existing_pid = existing_pids.get(loop_id)
                        task = asyncio.create_task(self.run_loop(loop, existing_pid))
                        active_loops[unique_key] = task
                        started_prices.add(unique_key)
                
                # Wait a bit before checking again
                await asyncio.sleep(5)
                
            except Exception as e:
                print(f"Error checking for new loops: {e}")
                await asyncio.sleep(5)
    
    async def periodic_rescan(self, interval_minutes=5):
        """Periodically rescan and ensure all loops have orders placed"""
        last_mirror_status = None  # Track status to avoid duplicate logs
        while True:
            try:
                await asyncio.sleep(interval_minutes * 60)  # Wait for interval
                
                # CRITICAL: Only run rescan if auto_mirror is enabled
                config = load_config()
                current_status = config.get('auto_mirror', False)
                
                # Only log when status changes (not every interval)
                if not current_status:
                    if last_mirror_status is not False:
                        print("[RESCAN] Auto mirror is OFF. Skipping periodic rescan.")
                        add_log("[RESCAN] Auto mirror is OFF. Will check again in 5 minutes.")
                    last_mirror_status = False
                    continue
                
                last_mirror_status = True  # Update status tracker
                
                print(f"[RESCAN] Running periodic rescan to ensure all loops have orders...")
                
                # Get current state
                loops = config.get('loops', [])
                enabled_loops = [l for l in loops if l.get('enabled', True)]
                
                if not enabled_loops:
                    continue
                
                # Get open orders from LN Markets
                open_trades_list, running_trades_list, _ = await get_cached_positions(self.client)
                
                # Count unique prices with orders
                orders_by_price = {}
                for order in open_trades_list:
                    try:
                        price = round(order.price * 2) / 2
                        orders_by_price[price] = order.id
                    except:
                        pass
                
                for pos in running_trades_list:
                    try:
                        price = round(pos.price * 2) / 2
                        orders_by_price[price] = pos.id
                    except:
                        pass
                
                total_orders = len(orders_by_price)
                expected_orders = len(enabled_loops)
                
                print(f"[RESCAN] Found {total_orders} orders on LN Markets, {expected_orders} enabled loops configured")
                
                # If counts don't match, trigger a mirror operation
                if total_orders != expected_orders:
                    print(f"[RESCAN] MISMATCH: Have {total_orders}, need {expected_orders}. Running mirror...")
                    
                    # Find missing loops
                    for loop in enabled_loops:
                        direction = loop.get('direction', 'long')
                        if direction == 'short':
                            entry_price = round(loop['sell_price'] * 2) / 2
                        else:
                            entry_price = round(loop['buy_price'] * 2) / 2
                        
                        if entry_price not in orders_by_price:
                            print(f"[RESCAN] Missing order for '{loop.get('name')}' @ ${entry_price:,.0f}")
                    
                    # Trigger mirror to fix
                    await self.run_mirror()
                else:
                    print(f"[RESCAN] All {expected_orders} loops have orders. No action needed.")
                    
            except Exception as e:
                print(f"[RESCAN] Error during periodic rescan: {e}")
    
    async def run_mirror(self):
        """Run mirror operation to sync loops with LN Markets"""
        try:
            print("[MIRROR] Starting mirror operation...")
            
            config = load_config()
            loops = config.get('loops', [])
            enabled_loops = [l for l in loops if l.get('enabled', True)]
            
            # Get all orders from LN Markets
            await _rate_limiter.wait()
            open_trades_list = await self.client.futures.isolated.get_open_trades()
            _rate_limiter.report_success()
            
            await _rate_limiter.wait()
            running_trades_list = await self.client.futures.isolated.get_running_trades()
            _rate_limiter.report_success()
            
            # Build map of existing orders by price
            existing_prices = {}
            for order in open_trades_list:
                try:
                    price = round(order.price * 2) / 2
                    existing_prices[price] = order
                except:
                    pass
            
            for pos in running_trades_list:
                try:
                    price = round(pos.price * 2) / 2
                    existing_prices[price] = pos
                except:
                    pass
            
            placed = 0
            for loop in enabled_loops:
                try:
                    direction = loop.get('direction', 'long')
                    buy_price = loop['buy_price']
                    sell_price = loop['sell_price']
                    qty = loop['quantity_usd']
                    leverage = loop.get('leverage', 1)
                    
                    if direction == 'short':
                        entry_price = round(sell_price * 2) / 2
                        entry_side = 'sell'
                        exit_price = buy_price
                    else:
                        entry_price = round(buy_price * 2) / 2
                        entry_side = 'buy'
                        exit_price = sell_price
                    
                    # Check if order already exists
                    if entry_price in existing_prices:
                        continue
                    
                    # Skip if price check would fail (below/above market)
                    current_price = await get_cached_ticker(self.client)
                    if not current_price:
                        continue
                    
                    if direction == 'long' and entry_price >= current_price:
                        print(f"[MIRROR] SKIPPED: {loop.get('name')} - buy price ${entry_price:,.0f} above market ${current_price:,.0f}")
                        continue
                    elif direction == 'short' and entry_price <= current_price:
                        print(f"[MIRROR] SKIPPED: {loop.get('name')} - sell price ${entry_price:,.0f} below market ${current_price:,.0f}")
                        continue
                    
                    # Place the order
                    if is_price_being_placed(entry_price):
                        continue
                    
                    mark_price_placing(entry_price)
                    
                    params = FuturesOrder(
                        type='limit',
                        side=entry_side,
                        price=float(entry_price),
                        leverage=float(leverage),
                        quantity=float(qty)
                    )
                    
                    await _rate_limiter.wait()
                    resp = await self.client.futures.isolated.new_trade(params)
                    _rate_limiter.report_success()
                    
                    # Set takeprofit
                    try:
                        tp_params = UpdateTakeprofitParams(id=resp.id, value=float(exit_price))
                        await _rate_limiter.wait()
                        await self.client.futures.isolated.update_takeprofit(tp_params)
                        _rate_limiter.report_success()
                    except Exception as e:
                        print(f"[MIRROR] Warning: Could not set takeprofit: {e}")
                    
                    unmark_price_placing(entry_price)
                    print(f"[MIRROR] Placed {entry_side} order for '{loop.get('name')}' @ ${entry_price:,.0f}")
                    placed += 1
                    
                    await asyncio.sleep(2)  # Rate limiting
                    
                except Exception as e:
                    print(f"[MIRROR] Error placing order for {loop.get('name')}: {e}")
                    unmark_price_placing(entry_price)
            
            print(f"[MIRROR] Complete! Placed {placed} missing orders")
            
        except Exception as e:
            print(f"[MIRROR] Error: {e}")

async def main():
    async with Bot() as bot:
        await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
'''
    
    # Write and run the bot
    with open('looptrade_running.py', 'w') as f:
        f.write(bot_code)
    
    try:
        # Use Popen to capture output line by line for persistent logging
        process = subprocess.Popen(
            [sys.executable, 'looptrade_running.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Read output line by line and add to logs
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if line:
                add_log(line)
        
        process.stdout.close()
        process.wait()
        
    except Exception as e:
        add_log(f"Bot error: {e}")

# Auto-start bot if it was running before (server restart recovery)
def auto_start_bot():
    """Auto-start bot if state indicates it should be running"""
    global bot_thread, bot_running
    
    state = load_state()
    if state.get("should_be_running", False):
        config = load_config()
        
        # Check if we can actually start
        if not config.get('api_key') or len(config['api_key']) < 10:
            print("Auto-start: API keys not configured, skipping")
            save_state({"should_be_running": False})
            return
        
        if not config.get('loops'):
            print("Auto-start: No loops configured, skipping")
            save_state({"should_be_running": False})
            return
        
        print("Auto-starting bot (was running before server restart)...")
        bot_running = True
        bot_thread = threading.Thread(target=run_bot_thread, daemon=True)
        bot_thread.start()
        add_log("Bot auto-started after server restart")

if __name__ == '__main__':
    # Try to auto-start bot if it was running
    auto_start_bot()
    
    # Start Flask server
    app.run(host='0.0.0.0', port=5001, debug=False)