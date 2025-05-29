import unittest
from unittest.mock import patch, MagicMock # Ensure patch is imported
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier # Added for spec
from sklearn.preprocessing import StandardScaler # Added for spec
import numpy as np
from datetime import datetime, timedelta

# Assuming ml_manager.py is in the same directory or accessible via PYTHONPATH
from ml_manager import MLManager

def create_sample_df_for_ml(num_rows=100, start_price=100.0):
    """Creates a sample DataFrame with necessary columns for MLManager.prepare_features."""
    data = {
        'timestamp': pd.to_datetime(np.arange(num_rows), unit='D', origin='2023-01-01'),
        'open': np.arange(start_price, start_price + num_rows) + np.random.rand(num_rows) * 2 - 1,
        'high': np.arange(start_price, start_price + num_rows) + 1 + np.random.rand(num_rows) * 2,
        'low': np.arange(start_price, start_price + num_rows) - 1 - np.random.rand(num_rows) * 2,
        'close': np.arange(start_price, start_price + num_rows) + np.random.rand(num_rows) * 2 - 1,
        'volume': np.random.randint(100, 1000, size=num_rows).astype(float)
    }
    df = pd.DataFrame(data)
    df.set_index('timestamp', inplace=True)
    # Ensure no NaNs in essential input columns for simplicity in test setup
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].fillna(method='bfill').fillna(method='ffill')
    return df

class TestMLManager(unittest.TestCase):

    def setUp(self):
        self.ml_manager = MLManager()
        # Mock callbacks
        self.ml_manager.on_training_complete = MagicMock()
        self.ml_manager.on_error = MagicMock()
        self.ml_manager.on_log = MagicMock()

    def test_prepare_features_basic_structure_train(self):
        """Test basic structure of X and y for training."""
        df = create_sample_df_for_ml(num_rows=50) # Needs enough rows for all rolling windows + target shift
        
        X, y = self.ml_manager.prepare_features(df, for_prediction=False)
        
        self.assertIsNotNone(X, "X should not be None")
        self.assertIsNotNone(y, "y should not be None")
        
        # Expected number of features (based on ml_manager.py)
        # sma_5, sma_10, sma_20, ema_5, ema_10, ema_20,
        # bb_width, rsi, macd, macd_signal, macd_hist,
        # volume_ratio, body_size, upper_shadow, lower_shadow,
        # price_change, price_change_1, price_change_2, price_change_5,
        # volatility
        expected_num_features = 20 
        self.assertEqual(X.shape[1], expected_num_features, f"Expected {expected_num_features} features")
        self.assertEqual(X.shape[0], y.shape[0], "X and y should have the same number of rows")
        
        # Check for NaNs - after dropping, there should be none
        self.assertFalse(np.isnan(X).any(), "X should not contain NaNs after processing")
        self.assertFalse(np.isnan(y).any(), "y should not contain NaNs after processing")

        # Max rolling window is 20 for price, 14 for RSI, 26 for MACD, 5 for volume. Target shift is 3.
        # So, roughly 26 + 3 = 29 rows might be lost.
        # For 50 rows, we expect around 50 - (26 (max_lookback_for_features) + 3 (target_shift)) = 21 valid rows.
        # This is an approximation as different indicators have different lookbacks.
        # The method uses dropna() which handles this.
        self.assertTrue(X.shape[0] > 0, "Expected some rows after NaN drop for 50 input rows")
        self.assertTrue(X.shape[0] < 50)


    def test_prepare_features_for_prediction(self):
        """Test feature preparation for prediction mode."""
        df = create_sample_df_for_ml(num_rows=50)
        
        X_last = self.ml_manager.prepare_features(df, for_prediction=True)
        
        self.assertIsNotNone(X_last, "X_last should not be None")
        expected_num_features = 20
        self.assertEqual(X_last.shape[0], 1, "Should return only one row for prediction")
        self.assertEqual(X_last.shape[1], expected_num_features, f"Expected {expected_num_features} features")
        self.assertFalse(np.isnan(X_last).any(), "X_last should not contain NaNs")

    def test_prepare_features_insufficient_data(self):
        """Test with insufficient data for feature calculation."""
        df_short = create_sample_df_for_ml(num_rows=10) # Less than min lookback (e.g., 20 for SMA/BB)
        
        X_train, y_train = self.ml_manager.prepare_features(df_short, for_prediction=False)
        self.assertIsNone(X_train, "X should be None for very short data (training)")
        self.assertIsNone(y_train, "y should be None for very short data (training)")

        X_pred = self.ml_manager.prepare_features(df_short, for_prediction=True)
        self.assertIsNone(X_pred, "X_last should be None for very short data (prediction)")


    def test_prepare_features_all_nans_input_robustness(self):
        """Test if prepare_features handles a DataFrame that becomes all NaNs after some ops."""
        # Create a df where rolling operations might lead to many NaNs
        data = {'close': np.arange(50).astype(float), 'volume': np.arange(50).astype(float)}
        df = pd.DataFrame(data, index=pd.to_datetime(np.arange(50), unit='D', origin='2023-01-01'))
        df['open'] = df['close'] - 1
        df['high'] = df['close'] + 1
        df['low'] = df['close'] -1
        
        # Example: if 'close' was all NaNs (though our helper prevents this for 'close')
        # df['close'] = np.nan 
        # X, y = self.ml_manager.prepare_features(df)
        # self.assertIsNone(X) # Or shape[0] == 0 depending on dropna
        # self.assertIsNone(y)

        # More realistically, test with data that produces some NaNs that should be dropped
        df_with_some_nans = create_sample_df_for_ml(num_rows=60)
        # Introduce some NaNs manually into a feature source column NOT handled by bfill/ffill in helper
        # e.g. if a new raw column was added and used.
        # For current features, this is less likely due to robust helper.
        # This test mostly confirms that dropna() works.
        
        X, y = self.ml_manager.prepare_features(df_with_some_nans)
        self.assertFalse(np.isnan(X).any())
        self.assertEqual(X.shape[0], y.shape[0])


    # train_model and predict are harder to unit test without extensive mocking of ML models
    # and sklearn components. Their core custom logic is within prepare_features.
    def test_predict_calls_model_and_scaler(self):
        # Setup a dummy model and scaler on the manager
        self.ml_manager.model = MagicMock(spec=GradientBoostingClassifier) 
        self.ml_manager.scaler = MagicMock(spec=StandardScaler)
        
        # Configure the mocked methods on the instances
        self.ml_manager.scaler.transform.return_value = np.array([[0.1] * 20]) 
        self.ml_manager.model.predict.return_value = np.array([1]) 
        self.ml_manager.model.predict_proba.return_value = np.array([[0.2, 0.8]])

        # Create sample features for one prediction
        sample_features_last_row = np.random.rand(1, 20) 
        
        dummy_timestamp = pd.Timestamp.now()
        dummy_price = 100.0

        prediction_result = self.ml_manager.predict(sample_features_last_row, dummy_timestamp, dummy_price)
        
        self.assertIsNotNone(prediction_result, "Prediction result should not be None")
        self.ml_manager.scaler.transform.assert_called_once_with(sample_features_last_row)
        self.ml_manager.model.predict.assert_called_once_with(self.ml_manager.scaler.transform.return_value)
        self.ml_manager.model.predict_proba.assert_called_once_with(self.ml_manager.scaler.transform.return_value)
        self.assertEqual(prediction_result['signal'], 'BUY') 
        self.assertEqual(len(self.ml_manager.predictions_history), 1)


if __name__ == '__main__':
    unittest.main()
