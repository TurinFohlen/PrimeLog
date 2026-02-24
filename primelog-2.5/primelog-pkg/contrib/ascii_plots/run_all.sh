wolfram -script ascii_plots/wl_bridge/errors.wl | python /ascii_plots/py_plots/errors.py
echo "=== FFT 频谱 ==="
wolfram -script ascii_plots/wl_bridge/fft.wl | python /ascii_plots/py_plots/fft.py
echo "=== 热力图 ==="
wolfram -script ascii_plots/wl_bridge/heatmap.wl | python /ascii_plots/py_plots/heatmap.py
echo "=== 时间序列 ==="
wolfram -script ascii_plots/wl_bridge/timeseries.wl | python /ascii_plots/py_plots/timeseries.py