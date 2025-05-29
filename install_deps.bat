@echo off
echo ============================================
echo 🚀 УСТАНОВКА ЗАВИСИМОСТЕЙ ДЛЯ ТОРГОВОГО БОТА
echo ============================================

echo.
echo 📦 Устанавливаем основные библиотеки...
pip install matplotlib pandas numpy requests

echo.
echo 📡 Устанавливаем WebSocket для стакана заявок...
pip install websocket-client

echo.
echo 🤖 Устанавливаем scikit-learn для ML функций...
pip install scikit-learn

echo.
echo ✅ УСТАНОВКА ЗАВЕРШЕНА!
echo.
echo 🎯 Теперь можно запустить бота:
echo python trading_bot.py
echo.
pause