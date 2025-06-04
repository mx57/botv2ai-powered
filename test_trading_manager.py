import unittest
from unittest.mock import MagicMock
import time
from datetime import datetime

from trading_manager import TradingManager


class TestTradingManager(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.tm = TradingManager(symbol='BTCUSDT', mode='simulation')
        
        # Mock callbacks to prevent errors
        self.tm.on_position_update = MagicMock()
        self.tm.on_order_update = MagicMock()
        self.tm.on_error = MagicMock()
        self.tm.on_log = MagicMock()
    
    def test_init(self):
        """Test TradingManager initialization."""
        self.assertEqual(self.tm.symbol, 'BTCUSDT')
        self.assertEqual(self.tm.mode, 'simulation')
        self.assertEqual(self.tm.balance, 1000.0)
        self.assertIsNone(self.tm.position)
        self.assertEqual(self.tm.total_trades, 0)
        self.assertEqual(self.tm.winning_trades, 0)
        self.assertEqual(self.tm.losing_trades, 0)
        self.assertEqual(self.tm.total_profit, 0.0)
    
    def test_set_trading_params(self):
        """Test setting trading parameters."""
        # Test setting all parameters
        self.tm.set_trading_params(
            leverage=20,
            risk_percent=2.0,
            take_profit_percent=3.0,
            stop_loss_percent=1.5,
            trailing_stop=True,
            trailing_percent=0.8
        )
        
        self.assertEqual(self.tm.leverage, 20)
        self.assertEqual(self.tm.risk_percent, 2.0)
        self.assertEqual(self.tm.take_profit_percent, 3.0)
        self.assertEqual(self.tm.stop_loss_percent, 1.5)
        self.assertTrue(self.tm.trailing_stop)
        self.assertEqual(self.tm.trailing_percent, 0.8)
    
    def test_set_trading_params_partial(self):
        """Test setting only some trading parameters."""
        original_leverage = self.tm.leverage
        original_risk = self.tm.risk_percent
        
        # Set only leverage and risk_percent
        self.tm.set_trading_params(leverage=15, risk_percent=1.5)
        
        self.assertEqual(self.tm.leverage, 15)
        self.assertEqual(self.tm.risk_percent, 1.5)
        # Other parameters should remain unchanged
        self.assertEqual(self.tm.take_profit_percent, 2.0)  # default value
        self.assertEqual(self.tm.stop_loss_percent, 1.0)    # default value
    
    def test_calculate_position_size(self):
        """Test position size calculation."""
        price = 50000.0
        self.tm.balance = 1000.0
        self.tm.risk_percent = 2.0
        self.tm.stop_loss_percent = 1.0
        self.tm.leverage = 10
        
        position_size = self.tm.calculate_position_size(price)
        
        # Expected calculation:
        # risk_amount = 1000 * (2/100) = 20
        # position_size = 20 / (50000 * 0.01) = 20 / 500 = 0.04
        # final_size = 0.04 / 10 = 0.004
        expected_size = 0.004
        self.assertAlmostEqual(position_size, expected_size, places=6)
    
    def test_open_long_position(self):
        """Test opening a long position."""
        price = 50000.0
        timestamp = time.time()
        
        result = self.tm.open_position('BUY', price, timestamp)
        
        self.assertTrue(result)
        self.assertIsNotNone(self.tm.position)
        self.assertEqual(self.tm.position['type'], 'LONG')
        self.assertEqual(self.tm.position['symbol'], 'BTCUSDT')
        self.assertEqual(self.tm.position['entry_price'], price)
        self.assertEqual(self.tm.position['timestamp'], timestamp)
        self.assertEqual(self.tm.position['status'], 'OPEN')
        
        # Check TP and SL levels for long position
        expected_tp = price * (1 + self.tm.take_profit_percent / 100)
        expected_sl = price * (1 - self.tm.stop_loss_percent / 100)
        self.assertEqual(self.tm.position['take_profit'], expected_tp)
        self.assertEqual(self.tm.position['stop_loss'], expected_sl)
        
        # Check that callbacks were called
        self.tm.on_position_update.assert_called_once_with(self.tm.position)
        self.tm.on_log.assert_called()
        
        # Check statistics
        self.assertEqual(self.tm.total_trades, 1)
    
    def test_open_short_position(self):
        """Test opening a short position."""
        price = 50000.0
        timestamp = time.time()
        
        result = self.tm.open_position('SELL', price, timestamp)
        
        self.assertTrue(result)
        self.assertIsNotNone(self.tm.position)
        self.assertEqual(self.tm.position['type'], 'SHORT')
        
        # Check TP and SL levels for short position
        expected_tp = price * (1 - self.tm.take_profit_percent / 100)
        expected_sl = price * (1 + self.tm.stop_loss_percent / 100)
        self.assertEqual(self.tm.position['take_profit'], expected_tp)
        self.assertEqual(self.tm.position['stop_loss'], expected_sl)
    
    def test_close_position_profit(self):
        """Test closing a position with profit."""
        # Open a long position first
        entry_price = 50000.0
        self.tm.open_position('BUY', entry_price, time.time())
        
        # Close at higher price (profit)
        close_price = 51000.0
        close_timestamp = time.time()
        
        result = self.tm.close_position(close_price, close_timestamp, 'MANUAL')
        
        self.assertTrue(result)
        self.assertIsNone(self.tm.position)
        
        # Check that position was added to history
        self.assertEqual(len(self.tm.positions_history), 1)
        closed_position = self.tm.positions_history[0]
        self.assertEqual(closed_position['status'], 'CLOSED')
        self.assertEqual(closed_position['exit_price'], close_price)
        self.assertEqual(closed_position['exit_timestamp'], close_timestamp)
        self.assertEqual(closed_position['close_reason'], 'MANUAL')
        
        # Check profit calculation
        self.assertGreater(closed_position['pnl'], 0)
        self.assertGreater(closed_position['pnl_percent'], 0)
        
        # Check statistics
        self.assertEqual(self.tm.winning_trades, 1)
        self.assertEqual(self.tm.losing_trades, 0)
        self.assertGreater(self.tm.total_profit, 0)
        self.assertGreater(self.tm.balance, 1000.0)  # Should be higher than initial
    
    def test_close_position_loss(self):
        """Test closing a position with loss."""
        # Open a long position first
        entry_price = 50000.0
        self.tm.open_position('BUY', entry_price, time.time())
        
        # Close at lower price (loss)
        close_price = 49000.0
        close_timestamp = time.time()
        
        result = self.tm.close_position(close_price, close_timestamp, 'STOP_LOSS')
        
        self.assertTrue(result)
        self.assertIsNone(self.tm.position)
        
        # Check that position was added to history
        closed_position = self.tm.positions_history[0]
        
        # Check loss calculation
        self.assertLess(closed_position['pnl'], 0)
        self.assertLess(closed_position['pnl_percent'], 0)
        
        # Check statistics
        self.assertEqual(self.tm.winning_trades, 0)
        self.assertEqual(self.tm.losing_trades, 1)
        self.assertLess(self.tm.total_profit, 0)
        self.assertLess(self.tm.balance, 1000.0)  # Should be lower than initial
    
    def test_close_position_no_position(self):
        """Test closing position when no position exists."""
        result = self.tm.close_position(50000.0, time.time())
        self.assertFalse(result)
    
    def test_process_signal_no_position(self):
        """Test processing signal when no position exists."""
        price = 50000.0
        timestamp = time.time()
        
        # Should open new position
        result = self.tm.process_signal('BUY', price, timestamp)
        self.assertTrue(result)
        self.assertIsNotNone(self.tm.position)
        self.assertEqual(self.tm.position['type'], 'LONG')
    
    def test_process_signal_with_position_same_direction(self):
        """Test processing signal when position exists in same direction."""
        # Open long position
        self.tm.open_position('BUY', 50000.0, time.time())
        
        # Process another BUY signal - should not open new position
        result = self.tm.process_signal('BUY', 51000.0, time.time())
        self.assertFalse(result)
        
        # Position should still exist and be the same
        self.assertIsNotNone(self.tm.position)
        self.assertEqual(self.tm.position['entry_price'], 50000.0)
    
    def test_process_signal_with_position_opposite_direction(self):
        """Test processing signal when position exists in opposite direction."""
        # Open long position
        self.tm.open_position('BUY', 50000.0, time.time())
        original_position = self.tm.position.copy()
        
        # Process SELL signal - should close current position (not open new one)
        result = self.tm.process_signal('SELL', 51000.0, time.time())
        self.assertTrue(result)
        
        # Position should be closed (not opened new one)
        self.assertIsNone(self.tm.position)
        
        # Original position should be in history
        self.assertEqual(len(self.tm.positions_history), 1)
    
    def test_update_position_long_profit(self):
        """Test updating long position with profit."""
        # Open long position
        entry_price = 50000.0
        self.tm.open_position('BUY', entry_price, time.time())
        
        # Disable throttling for testing
        self.tm.position_update_interval = 0
        
        # Update with higher price (but not high enough to trigger TP)
        # TP is at entry_price * (1 + 2%) = 51000, so use 50500
        current_price = 50500.0
        self.tm.update_position(current_price)
        
        # Position should still exist
        self.assertIsNotNone(self.tm.position)
        
        # Check PnL calculation
        self.assertGreater(self.tm.position['pnl'], 0)
        self.assertGreater(self.tm.position['pnl_percent'], 0)
        
        # Check that position update callback was called
        self.tm.on_position_update.assert_called()
    
    def test_update_position_short_profit(self):
        """Test updating short position with profit."""
        # Open short position
        entry_price = 50000.0
        self.tm.open_position('SELL', entry_price, time.time())
        
        # Disable throttling for testing
        self.tm.position_update_interval = 0
        
        # Update with lower price (profit for short, but not low enough to trigger TP)
        # TP is at entry_price * (1 - 2%) = 49000, so use 49500
        current_price = 49500.0
        self.tm.update_position(current_price)
        
        # Position should still exist
        self.assertIsNotNone(self.tm.position)
        
        # Check PnL calculation
        self.assertGreater(self.tm.position['pnl'], 0)
        self.assertGreater(self.tm.position['pnl_percent'], 0)
    
    def test_update_position_no_position(self):
        """Test updating position when no position exists."""
        # Should not raise error
        self.tm.update_position(50000.0)
        # No assertions needed, just checking it doesn't crash
    
    def test_get_trading_stats(self):
        """Test getting trading statistics."""
        # Initial stats
        stats = self.tm.get_trading_stats()
        expected_stats = {
            'balance': 1000.0,
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0,
            'total_profit': 0.0,
            'max_drawdown': 0.0
        }
        self.assertEqual(stats, expected_stats)
        
        # After some trades
        self.tm.total_trades = 10
        self.tm.winning_trades = 6
        self.tm.losing_trades = 4
        
        stats = self.tm.get_trading_stats()
        self.assertEqual(stats['win_rate'], 60.0)
    
    def test_get_position_info_no_position(self):
        """Test getting position info when no position exists."""
        position_info = self.tm.get_position_info()
        self.assertIsNone(position_info)
    
    def test_get_position_info_with_position(self):
        """Test getting position info when position exists."""
        # Open position
        self.tm.open_position('BUY', 50000.0, time.time())
        
        position_info = self.tm.get_position_info()
        self.assertIsNotNone(position_info)
        self.assertEqual(position_info['type'], 'LONG')
        self.assertEqual(position_info['entry_price'], 50000.0)
    
    def test_trailing_stop_activation(self):
        """Test trailing stop activation and adjustment."""
        # Enable trailing stop
        self.tm.trailing_stop = True
        self.tm.trailing_percent = 1.0
        self.tm.take_profit_percent = 2.0  # Activation at 1% (half of TP)
        
        # Open long position
        entry_price = 50000.0
        self.tm.open_position('BUY', entry_price, time.time())
        
        # Disable throttling for testing
        self.tm.position_update_interval = 0
        
        # Update with price that should activate trailing stop
        # Activation happens at take_profit_percent / 2 = 1%
        profitable_price = 50500.0  # 1% increase
        self.tm.update_position(profitable_price)
        
        # Trailing should be activated
        self.assertTrue(self.tm.position['trailing_activation'])
        self.assertEqual(self.tm.position['trailing_price'], profitable_price)
        
        # Update with higher price to test trailing adjustment
        higher_price = 50600.0
        self.tm.update_position(higher_price)
        
        # Trailing price should be updated to the higher price
        self.assertEqual(self.tm.position['trailing_price'], higher_price)
    
    def test_stop_loss_trigger(self):
        """Test automatic position closure on stop loss."""
        # Open long position
        entry_price = 50000.0
        self.tm.open_position('BUY', entry_price, time.time())
        
        # Disable throttling for testing
        self.tm.position_update_interval = 0
        
        # Update with price below stop loss
        stop_loss_price = self.tm.position['stop_loss'] - 100  # Below SL
        self.tm.update_position(stop_loss_price)
        
        # Position should be closed
        self.assertIsNone(self.tm.position)
        self.assertEqual(len(self.tm.positions_history), 1)
        self.assertEqual(self.tm.positions_history[0]['close_reason'], 'STOP_LOSS')
    
    def test_take_profit_trigger(self):
        """Test automatic position closure on take profit."""
        # Open long position
        entry_price = 50000.0
        self.tm.open_position('BUY', entry_price, time.time())
        
        # Disable throttling for testing
        self.tm.position_update_interval = 0
        
        # Update with price above take profit
        take_profit_price = self.tm.position['take_profit'] + 100  # Above TP
        self.tm.update_position(take_profit_price)
        
        # Position should be closed
        self.assertIsNone(self.tm.position)
        self.assertEqual(len(self.tm.positions_history), 1)
        self.assertEqual(self.tm.positions_history[0]['close_reason'], 'TAKE_PROFIT')
    
    def test_position_update_throttling(self):
        """Test that position updates are throttled."""
        # Open position
        self.tm.open_position('BUY', 50000.0, time.time())
        
        # Reset mock call count
        self.tm.on_position_update.reset_mock()
        
        # Update position multiple times quickly
        self.tm.update_position(50100.0)
        self.tm.update_position(50200.0)
        self.tm.update_position(50300.0)
        
        # Should only call callback once due to throttling
        # (unless enough time has passed)
        call_count = self.tm.on_position_update.call_count
        self.assertLessEqual(call_count, 1)


if __name__ == '__main__':
    unittest.main()