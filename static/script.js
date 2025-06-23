// Placeholder for Chart instance
let klineChartInstance = null;

async function fetchData(url, options = {}) {
    const displayErrorInElement = options.errorElementId; // Custom option to pass error display element
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            let errorDetail = response.statusText;
            try {
                const errorData = await response.json();
                errorDetail = errorData.detail || errorDetail;
            } catch (e) {
                // Ignore if response is not JSON
            }
            throw new Error(`HTTP error ${response.status}: ${errorDetail}`);
        }
        return await response.json();
    } catch (error) {
        console.error('API Error for URL ' + url + ':', error);
        const errorMessage = { error: error.message };
        if (displayErrorInElement) {
            displayData(displayErrorInElement, errorMessage);
        }
        return errorMessage; // Return error structure for further handling
    }
}

function displayData(elementId, data) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = JSON.stringify(data, null, 2);
    } else {
        console.error(`Element with ID ${elementId} not found for displaying data.`);
    }
}

async function fetchSettings() {
    const data = await fetchData('/api/settings', { errorElementId: 'settings-display' });
    displayData('settings-display', data);
}

async function fetchKlines() {
    const klinesDisplayElement = 'klines-display';
    const data = await fetchData('/api/klines', { errorElementId: klinesDisplayElement });

    if (data && !data.error && data.data && Array.isArray(data.data)) {
        if (data.data.length === 0) {
            displayData(klinesDisplayElement, { message: "No k-line data returned from API.", symbol: data.symbol, interval: data.interval });
            renderKlineChart(null); // Clear or hide chart
        } else {
            displayData(klinesDisplayElement, { symbol: data.symbol, interval: data.interval, klines_displayed: data.data.slice(-5) }); // Display last 5 klines
            renderKlineChart(data.data);
        }
    } else {
        // Error already displayed by fetchData or data is malformed
        displayData(klinesDisplayElement, data); // Display the error or unexpected data structure
        renderKlineChart(null); // Clear or hide chart
    }
}

function renderKlineChart(klineData) {
    const chartElement = document.getElementById('kline-chart');
    const klinesDisplayElement = 'klines-display'; // For messages about the chart

    if (!chartElement) return; // Chart canvas not found
    const ctx = chartElement.getContext('2d');

    if (klineChartInstance) {
        klineChartInstance.destroy();
        klineChartInstance = null;
    }

    if (!Array.isArray(klineData) || klineData.length === 0) {
        // Optionally clear the canvas or display a message
        // ctx.clearRect(0, 0, chartElement.width, chartElement.height);
        // No data to display, message should be in klines-display
        return;
    }

    try {
        const labels = klineData.map(k => new Date(k.timestamp).toLocaleTimeString());
        const closePrices = klineData.map(k => parseFloat(k.close));

        klineChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Close Price',
                    data: closePrices,
                    borderColor: 'rgb(75, 192, 192)',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { title: { display: true, text: 'Time' } },
                    y: { title: { display: true, text: 'Price' } }
                }
            }
        });
    } catch (e) {
        console.error("Error rendering chart:", e);
        displayData(klinesDisplayElement, { error: "Failed to render k-line chart. " + e.message });
    }
}

async function trainModel() {
    const data = await fetchData('/api/ml/train', { method: 'POST', errorElementId: 'ml-prediction-display' });
    displayData('ml-prediction-display', data);
}

async function fetchPrediction() {
    const data = await fetchData('/api/ml/predict', { errorElementId: 'ml-prediction-display' });
    displayData('ml-prediction-display', data);
}

async function fetchDensityZones() {
    const data = await fetchData('/api/density_zones', { errorElementId: 'density-zones-display' });
    displayData('density-zones-display', data);
}

async function fetchTradingStatus() {
    const data = await fetchData('/api/trading/status', { errorElementId: 'trading-status-display' });
    displayData('trading-status-display', data);
}

async function makeTrade() {
    const displayElementId = 'trading-status-display';
    const signal = document.getElementById('trade-signal').value.toUpperCase(); // Ensure signal is uppercase
    const price = parseFloat(document.getElementById('trade-price').value);
    if (!signal || isNaN(price)) {
        displayData(displayElementId, { error: 'Please enter valid signal (BUY/SELL) and price.' });
        return;
    }
    const data = await fetchData('/api/trading/trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signal, price }),
        errorElementId: displayElementId
    });
    // Fetch status again to show the latest state after trade attempt
    if (!data.error) {
        fetchTradingStatus();
    } else {
        displayData(displayElementId, data);
    }
}

async function closeTrade() {
    const displayElementId = 'trading-status-display';
    const price = parseFloat(document.getElementById('close-price').value);
    if (isNaN(price)) {
        displayData(displayElementId, { error: 'Please enter a valid price.' });
        return;
    }
    const data = await fetchData('/api/trading/close_position', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ price }),
        errorElementId: displayElementId
    });
    // Fetch status again to show the latest state after close attempt
    if (!data.error) {
        fetchTradingStatus();
    } else {
        displayData(displayElementId, data);
    }
}

// Initial fetches on page load
document.addEventListener('DOMContentLoaded', () => {
    fetchSettings();
    fetchTradingStatus();
    // Optionally, fetch klines on load, or wait for button click
    // fetchKlines();
});
