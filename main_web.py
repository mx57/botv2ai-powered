from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import logging
import pandas as pd
from datetime import datetime
from pydantic import BaseModel

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Import Bot Managers ---
try:
    from settings_manager import SettingsManager
    from data_manager import DataManager
    from ml_manager import MLManager
    from trading_manager import TradingManager
except ImportError as e:
    logger.error(f"Failed to import bot managers: {e}", exc_info=True)
    SettingsManager, DataManager, MLManager, TradingManager = None, None, None, None

app = FastAPI(title="Trading Bot Web API")

# --- Pydantic Models for Request Bodies ---
class TradeSignalRequest(BaseModel):
    signal: str # BUY or SELL
    price: float

class ClosePositionRequest(BaseModel):
    price: float

# --- FastAPI Application State ---
# Using app.state to store manager instances

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
async def startup_event():
    """
    Initialize manager instances when the FastAPI application starts.
    """
    if SettingsManager:
        app.state.settings_manager = SettingsManager()
        logger.info("SettingsManager initialized.")

        if DataManager and app.state.settings_manager:
            try:
                app.state.data_manager = DataManager(
                    symbol=app.state.settings_manager.settings['trading']['symbol'],
                    interval=app.state.settings_manager.settings['trading']['interval']
                )
                logger.info("DataManager initialized.")
            except Exception as e:
                logger.error(f"Error initializing DataManager: {e}", exc_info=True)
                app.state.data_manager = None
        else:
            logger.warning("DataManager class not available or SettingsManager failed to initialize.")
            app.state.data_manager = None

        if MLManager:
            try:
                app.state.ml_manager = MLManager()
                logger.info("MLManager initialized.")
            except Exception as e:
                logger.error(f"Error initializing MLManager: {e}", exc_info=True)
                app.state.ml_manager = None
        else:
            logger.warning("MLManager class not available.")
            app.state.ml_manager = None

        if TradingManager and app.state.settings_manager:
            try:
                app.state.trading_manager = TradingManager(
                    symbol=app.state.settings_manager.settings['trading']['symbol'],
                    mode=app.state.settings_manager.settings['trading']['mode']
                )
                logger.info("TradingManager initialized.")
            except Exception as e:
                logger.error(f"Error initializing TradingManager: {e}", exc_info=True)
                app.state.trading_manager = None
        else:
            logger.warning("TradingManager class not available or SettingsManager failed to initialize.")
            app.state.trading_manager = None
    else:
        logger.warning("SettingsManager class not available. Core managers will not be initialized.")
        app.state.settings_manager = None
        app.state.data_manager = None
        app.state.ml_manager = None
        app.state.trading_manager = None

# --- API Endpoints ---

@app.get("/", response_class=FileResponse)
async def read_index():
    """Serves the main HTML page."""
    return "static/index.html"

@app.get("/api/settings")
async def get_all_settings():
    """Retrieve all current bot settings."""
    if not hasattr(app.state, 'settings_manager') or app.state.settings_manager is None:
        raise HTTPException(status_code=503, detail="SettingsManager not available.")
    return app.state.settings_manager.get_settings()

@app.get("/api/settings/{category}")
async def get_settings_category(category: str):
    """Retrieve settings for a specific category."""
    if not hasattr(app.state, 'settings_manager') or app.state.settings_manager is None:
        raise HTTPException(status_code=503, detail="SettingsManager not available.")
    settings = app.state.settings_manager.get_settings(category)
    if not settings and category not in app.state.settings_manager.settings: # Check if category exists
        raise HTTPException(status_code=404, detail=f"Settings category '{category}' not found.")
    return settings

@app.get("/api/klines")
async def get_klines_data():
    """Retrieve the latest k-line (candlestick) data."""
    if not hasattr(app.state, 'data_manager') or app.state.data_manager is None:
        raise HTTPException(status_code=503, detail="DataManager not available.")
    try:
        df = app.state.data_manager.get_kline_data()
        if df is not None and not df.empty:
            df_reset = df.reset_index()
            df_reset['timestamp'] = df_reset['timestamp'].astype(str)
            return {"data": df_reset.to_dict(orient='records'), "symbol": app.state.data_manager.symbol, "interval": app.state.data_manager.interval}
        elif df is not None and df.empty:
            return {"message": "No k-line data currently available (DataFrame is empty).", "symbol": app.state.data_manager.symbol, "interval": app.state.data_manager.interval, "data": []}
        else:
            logger.warning("get_kline_data returned None.")
            raise HTTPException(status_code=404, detail="Failed to retrieve k-line data or no data available.")
    except Exception as e:
        logger.error(f"Error in /api/klines endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

@app.get("/api/density_zones")
async def get_density_zones_data():
    """Retrieve the calculated density zones."""
    if not hasattr(app.state, 'data_manager') or app.state.data_manager is None:
        raise HTTPException(status_code=503, detail="DataManager not available.")
    try:
        if app.state.data_manager.df is not None and not app.state.data_manager.df.empty and not app.state.data_manager.density_zones:
            logger.info("Density zones are empty but DataFrame exists, attempting recalculation.")
            app.state.data_manager.calculate_density_zones()

        zones = app.state.data_manager.density_zones
        return {"data": zones, "symbol": app.state.data_manager.symbol, "interval": app.state.data_manager.interval}
    except Exception as e:
        logger.error(f"Error in /api/density_zones endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

@app.post("/api/ml/train")
async def train_ml_model(background_tasks: BackgroundTasks):
    """Start ML model training in the background."""
    if not hasattr(app.state, 'ml_manager') or app.state.ml_manager is None:
        raise HTTPException(status_code=503, detail="MLManager not available.")
    if not hasattr(app.state, 'data_manager') or app.state.data_manager is None or app.state.data_manager.df is None or app.state.data_manager.df.empty:
        raise HTTPException(status_code=400, detail="DataManager not available or no data to train on.")

    df_copy = app.state.data_manager.df.copy() # Pass a copy to avoid issues with ongoing updates
    background_tasks.add_task(app.state.ml_manager.train_model, df_copy)
    return {"message": "ML model training started in the background."}

@app.get("/api/ml/predict")
async def get_ml_prediction():
    """Get a prediction from the ML model based on the latest data."""
    if not hasattr(app.state, 'ml_manager') or app.state.ml_manager is None:
        raise HTTPException(status_code=503, detail="MLManager not available.")
    if not hasattr(app.state, 'data_manager') or app.state.data_manager is None or app.state.data_manager.df is None or app.state.data_manager.df.empty:
        raise HTTPException(status_code=400, detail="DataManager not available or no data for prediction.")

    df = app.state.data_manager.df
    if len(df) < 30: # Check if data is sufficient, align with prepare_features logic
        raise HTTPException(status_code=400, detail="Insufficient data for feature preparation.")

    try:
        latest_features = app.state.ml_manager.prepare_features(df.copy(), for_prediction=True)
        if latest_features is None:
            raise HTTPException(status_code=500, detail="Failed to prepare features for prediction.")

        current_price = df.iloc[-1]['close'] if not df.empty else 0
        prediction = app.state.ml_manager.predict(latest_features, current_timestamp=pd.Timestamp.now(tz='UTC'), current_price=current_price)

        if prediction:
            return prediction
        else:
            raise HTTPException(status_code=500, detail="Failed to get a prediction from the model.")
    except Exception as e:
        logger.error(f"Error in /api/ml/predict endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred during prediction: {str(e)}")

@app.get("/api/trading/status")
async def get_trading_status():
    """Get current trading position and statistics."""
    if not hasattr(app.state, 'trading_manager') or app.state.trading_manager is None:
        raise HTTPException(status_code=503, detail="TradingManager not available.")
    return {
        "position": app.state.trading_manager.get_position_info(),
        "stats": app.state.trading_manager.get_trading_stats()
    }

@app.post("/api/trading/trade")
async def execute_trade_signal(trade_data: TradeSignalRequest):
    """Process a trading signal (BUY/SELL)."""
    if not hasattr(app.state, 'trading_manager') or app.state.trading_manager is None:
        raise HTTPException(status_code=503, detail="TradingManager not available.")
    try:
        # Ensure signal is uppercase as expected by process_signal
        result = app.state.trading_manager.process_signal(trade_data.signal.upper(), trade_data.price)
        return {
            "success": result,
            "message": f"Signal {trade_data.signal} at price {trade_data.price} processed. Success: {result}",
            "position": app.state.trading_manager.get_position_info()
        }
    except Exception as e:
        logger.error(f"Error in /api/trading/trade endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred processing trade: {str(e)}")

@app.post("/api/trading/close_position")
async def close_current_position(close_data: ClosePositionRequest):
    """Close the current open position at the given price."""
    if not hasattr(app.state, 'trading_manager') or app.state.trading_manager is None:
        raise HTTPException(status_code=503, detail="TradingManager not available.")
    if app.state.trading_manager.position is None:
        raise HTTPException(status_code=400, detail="No open position to close.")
    try:
        result = app.state.trading_manager.close_position(close_data.price, timestamp=datetime.now())
        return {
            "success": result,
            "message": f"Close position attempt at price {close_data.price}. Success: {result}",
            "position": app.state.trading_manager.get_position_info()
        }
    except Exception as e:
        logger.error(f"Error in /api/trading/close_position endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred closing position: {str(e)}")


if __name__ == "__main__":
    logger.info("Starting Uvicorn server for development from __main__...")
    uvicorn.run("main_web:app", host="0.0.0.0", port=8000, reload=True)

# To run from command line:
# uvicorn main_web:app --reload --host 0.0.0.0 --port 8000
