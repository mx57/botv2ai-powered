import time
import threading
import json
import requests
from datetime import datetime
from collections import deque
import logging

logger = logging.getLogger(__name__)

class TradingManager:
    """Модуль для управления торговыми операциями"""
    
    def __init__(self, symbol='BTCUSDT', mode='simulation'):
        self.symbol = symbol
        self.mode = mode  # 'simulation' или 'real'
        
        # Параметры торговли
        self.leverage = 10
        self.risk_percent = 1.0  # Процент риска от баланса
        self.take_profit_percent = 2.0
        self.stop_loss_percent = 1.0
        self.trailing_stop = False
        self.trailing_percent = 0.5
        
        # Состояние торговли
        self.balance = 1000.0  # Начальный баланс для симуляции
        self.position = None  # Текущая позиция
        self.positions_history = deque(maxlen=100)  # История позиций
        self.orders = []  # Активные ордера
        
        # Статистика
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit = 0.0
        self.max_drawdown = 0.0
        
        # Оптимизация производительности
        self.last_position_update = 0
        self.position_update_interval = 3.0  # Минимальный интервал между обновлениями (сек)
        
        # Колбэки для обновления UI
        self.on_position_update = None
        self.on_order_update = None
        # self.on_error = None # Replaced by logger
        # self.on_log = None # Replaced by logger
    
    def set_trading_params(self, leverage=None, risk_percent=None, 
                          take_profit_percent=None, stop_loss_percent=None,
                          trailing_stop=None, trailing_percent=None):
        """Установка параметров торговли"""
        if leverage is not None:
            self.leverage = max(1, min(125, leverage))
        
        if risk_percent is not None:
            self.risk_percent = max(0.1, min(10, risk_percent))
        
        if take_profit_percent is not None:
            self.take_profit_percent = max(0.1, take_profit_percent)
        
        if stop_loss_percent is not None:
            self.stop_loss_percent = max(0.1, stop_loss_percent)
        
        if trailing_stop is not None:
            self.trailing_stop = trailing_stop
        
        if trailing_percent is not None:
            self.trailing_percent = max(0.1, trailing_percent)
        
        logger.info(f"Параметры торговли обновлены: Leverage: {self.leverage}, Risk: {self.risk_percent}%, TP: {self.take_profit_percent}%, SL: {self.stop_loss_percent}%")
    
    def process_signal(self, signal, price, timestamp=None):
        """Обработка торгового сигнала"""
        if signal not in ['BUY', 'SELL', 'CLOSE']:
            return False
        
        if timestamp is None:
            timestamp = datetime.now()
        
        # Проверка текущей позиции
        if self.position:
            # Если сигнал противоположен текущей позиции или это сигнал закрытия
            if (self.position['type'] == 'LONG' and signal in ['SELL', 'CLOSE']) or \
               (self.position['type'] == 'SHORT' and signal in ['BUY', 'CLOSE']):
                return self.close_position(price, timestamp, signal)
            # Если сигнал совпадает с текущей позицией, игнорируем
            return False
        
        # Если нет открытой позиции и сигнал не CLOSE
        if signal != 'CLOSE':
            return self.open_position(signal, price, timestamp)
        
        return False
    
    def open_position(self, signal, price, timestamp):
        """Открытие новой позиции"""
        try:
            position_type = 'LONG' if signal == 'BUY' else 'SHORT'
            
            # Расчет размера позиции
            position_size = self.calculate_position_size(price)
            
            # Расчет уровней TP и SL
            if position_type == 'LONG':
                take_profit = price * (1 + self.take_profit_percent / 100)
                stop_loss = price * (1 - self.stop_loss_percent / 100)
            else:  # SHORT
                take_profit = price * (1 - self.take_profit_percent / 100)
                stop_loss = price * (1 + self.stop_loss_percent / 100)
            
            # Создание позиции
            self.position = {
                'type': position_type,
                'symbol': self.symbol,
                'entry_price': price,
                'size': position_size,
                'take_profit': take_profit,
                'stop_loss': stop_loss,
                'trailing_stop': self.trailing_stop,
                'trailing_activation': False,
                'trailing_price': None,
                'timestamp': timestamp,
                'pnl': 0.0,
                'pnl_percent': 0.0,
                'status': 'OPEN'
            }
            
            # Обновление статистики
            self.total_trades += 1
            
            # Логирование
            logger.info(f"Открыта {position_type} позиция по {self.symbol} по цене {price:.2f}. Size: {position_size:.4f}, TP: {take_profit:.2f}, SL: {stop_loss:.2f}")
            
            # Вызов колбэка обновления позиции
            if self.on_position_update:
                self.on_position_update(self.position)
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка открытия позиции: {e}", exc_info=True)
            return False
    
    def close_position(self, price, timestamp, reason='SIGNAL'):
        """Закрытие текущей позиции"""
        if not self.position:
            return False
        
        try:
            # Расчет P&L
            if self.position['type'] == 'LONG':
                pnl = (price - self.position['entry_price']) * self.position['size'] * self.leverage
                pnl_percent = (price - self.position['entry_price']) / self.position['entry_price'] * 100 * self.leverage
            else:  # SHORT
                pnl = (self.position['entry_price'] - price) * self.position['size'] * self.leverage
                pnl_percent = (self.position['entry_price'] - price) / self.position['entry_price'] * 100 * self.leverage
            
            # Обновление баланса
            self.balance += pnl
            
            # Обновление статистики
            if pnl > 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1
            
            self.total_profit += pnl
            
            # Расчет просадки
            if self.balance < self.max_drawdown:
                self.max_drawdown = self.balance
            
            # Обновление позиции
            self.position['exit_price'] = price
            self.position['exit_timestamp'] = timestamp
            self.position['pnl'] = pnl
            self.position['pnl_percent'] = pnl_percent
            self.position['status'] = 'CLOSED'
            self.position['close_reason'] = reason
            
            # Добавление в историю
            self.positions_history.append(self.position.copy())
            
            # Логирование
            log_level = "INFO" if pnl > 0 else "WARNING"
            logger.log(getattr(logging, log_level.upper(), logging.INFO),
                       f"Закрыта {self.position['type']} позиция по {self.symbol} ({reason}). Price: {price:.2f}, P&L: {pnl:.2f} ({pnl_percent:.2f}%)")
            
            # Вызов колбэка обновления позиции
            if self.on_position_update:
                self.on_position_update(self.position) # Pass the closed position state
            
            # Сброс текущей позиции
            self.position = None
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка закрытия позиции: {e}", exc_info=True)
            return False
    
    def update_position(self, price):
        """Обновление состояния текущей позиции"""
        # Проверка на слишком частые обновления
        current_time = time.time()
        if (current_time - self.last_position_update) < self.position_update_interval:
            return
        
        if not self.position or self.position['status'] != 'OPEN':
            return
        
        try:
            # Расчет текущего P&L
            if self.position['type'] == 'LONG':
                pnl = (price - self.position['entry_price']) * self.position['size'] * self.leverage
                pnl_percent = (price - self.position['entry_price']) / self.position['entry_price'] * 100 * self.leverage
            else:  # SHORT
                pnl = (self.position['entry_price'] - price) * self.position['size'] * self.leverage
                pnl_percent = (self.position['entry_price'] - price) / self.position['entry_price'] * 100 * self.leverage
            
            self.position['pnl'] = pnl
            self.position['pnl_percent'] = pnl_percent
            
            # Проверка условий закрытия позиции
            # Take Profit
            if (self.position['type'] == 'LONG' and price >= self.position['take_profit']) or \
               (self.position['type'] == 'SHORT' and price <= self.position['take_profit']):
                self.close_position(price, datetime.now(), 'TAKE_PROFIT')
                return
            
            # Stop Loss
            if (self.position['type'] == 'LONG' and price <= self.position['stop_loss']) or \
               (self.position['type'] == 'SHORT' and price >= self.position['stop_loss']):
                self.close_position(price, datetime.now(), 'STOP_LOSS')
                return
            
            # Trailing Stop
            if self.position['trailing_stop']:
                # Активация трейлинг-стопа при достижении определенного уровня прибыли
                if not self.position['trailing_activation']:
                    activation_percent = self.take_profit_percent / 2
                    if (self.position['type'] == 'LONG' and pnl_percent >= activation_percent) or \
                       (self.position['type'] == 'SHORT' and pnl_percent >= activation_percent):
                        self.position['trailing_activation'] = True
                        self.position['trailing_price'] = price
                        
                        logger.info(f"Активирован трейлинг-стоп по цене {price:.2f} для позиции {self.position['type']} {self.symbol}")
                
                # Обновление трейлинг-стопа
                if self.position['trailing_activation']:
                    if self.position['type'] == 'LONG':
                        if price > self.position['trailing_price']:
                            # Обновление трейлинг-цены
                            self.position['trailing_price'] = price
                            # Обновление стоп-лосса
                            new_stop = price * (1 - self.trailing_percent / 100)
                            if new_stop > self.position['stop_loss']:
                                self.position['stop_loss'] = new_stop
                        
                        # Проверка трейлинг-стопа
                        if price <= self.position['stop_loss']:
                            self.close_position(price, datetime.now(), 'TRAILING_STOP')
                            return
                    
                    else:  # SHORT
                        if price < self.position['trailing_price']:
                            # Обновление трейлинг-цены
                            self.position['trailing_price'] = price
                            # Обновление стоп-лосса
                            new_stop = price * (1 + self.trailing_percent / 100)
                            if new_stop < self.position['stop_loss']:
                                self.position['stop_loss'] = new_stop
                        
                        # Проверка трейлинг-стопа
                        if price >= self.position['stop_loss']:
                            self.close_position(price, datetime.now(), 'TRAILING_STOP')
                            return
            
            # Вызов колбэка обновления позиции
            if self.on_position_update:
                self.on_position_update(self.position)
            
            self.last_position_update = current_time
            
        except Exception as e:
            logger.error(f"Ошибка обновления позиции: {e}", exc_info=True)
    
    def calculate_position_size(self, price):
        """Расчет размера позиции на основе риска"""
        risk_amount = self.balance * (self.risk_percent / 100)
        position_size = risk_amount / (price * self.stop_loss_percent / 100)
        return position_size / self.leverage
    
    def get_trading_stats(self):
        """Получение статистики торговли"""
        win_rate = 0 if self.total_trades == 0 else (self.winning_trades / self.total_trades) * 100
        
        return {
            'balance': self.balance,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'total_profit': self.total_profit,
            'max_drawdown': self.max_drawdown
        }
    
    def get_position_info(self):
        """Получение информации о текущей позиции"""
        if not self.position:
            return None
        
        return self.position