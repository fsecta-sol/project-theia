# 📊 Data Model untuk Dashboard Theia

## Ringkasan Data Model

Berdasarkan analisis file-file sebelumnya, berikut adalah data model yang perlu divisualisasikan dalam dashboard Theia:

## 1. Closed Trades (Dari tabel `archives`)
- **Equity Curve**: Grafik kumulatif PnL dari closed trades
- **PnL Distribution**: Distribusi frekuensi berdasarkan bucket (misalnya >5x, 2x-5x, 0-2x, -50%-0, <-50%)
- **Exit Reasons Analysis**: Distribusi alasan exit (hard_stop, voided_invalid_sol_usd, dll)
- **Jumlah closed trades per hari**: Untuk daily monitoring
- **Average PnL per trade**: Rata-rata keuntungan/kerugian
- **Win rate**: Persentase trade untung vs rugi
- **Profit Factor**: Rasio total profit / total loss

## 2. Wallet Profiling (Dari tabel `wallet_profiles`)
- **Wallet Attribution**: Performa per wallet (win rate, expectancy, total PnL)
- **Top performing wallets**: Wallet dengan kinerja terbaik
- **Wallet activity heatmap**: Aktivitas trading per wallet
- **Risk metrics per wallet**: Volatilitas, drawdown, dll
- **Pattern clustering**: Kategorisasi pola trading wallet

## 3. Hypotheses Testing (Dari tabel `hypotheses`)
- **Strategy Performance**: Expectancy, profit factor, win rate per hypothesis
- **Forward vs In-sample**: Perbandingan kinerja di-sample berbeda
- **Strategy effectiveness**: Efektivitas masing-masing pendekatan
- **Backtest results**: Hasil uji historis dari berbagai strategi

## 4. Open Positions (Dari tabel `paper_trades`)
- **Current open positions**: Posisi yang sedang aktif
- **Position aging**: Lama waktu posisi terbuka
- **Unrealized PnL**: Keuntungan/kerugian belum direalisasi
- **Risk exposure**: Paparan risiko saat ini

## 5. Daily Data Monitoring
- **Today's entries count**: Jumlah data yang masuk hari ini
- **Last entry timestamp**: Kapan data terakhir masuk
- **Data types count**: Jumlah jenis data yang termonitor
- **Recent formats**: Format data terbaru
- **Recent entries list**: Daftar entri terbaru dengan tipe dan waktu

## 6. Price Data (Dari tabel `price_snapshots_v2`)
- **Historical charts**: Grafik harga token seiring waktu
- **OHLCV visualization**: Open, High, Low, Close, Volume
- **Price movements**: Pergerakan harga relatif terhadap waktu
- **Liquidity tracking**: Perubahan likuiditas token

## 7. Screening Data (Dari tabel `screens`)
- **Screening effectiveness**: Efektivitas filter/token screening
- **Survival rates**: Rasio token yang bertahan vs yang rug (rugged)
- **False positive/negative rates**: Akurasi dari screening

## 8. Token Data (Dari tabel `tokens`)
- **Token universe**: Daftar token yang tertrack
- **Token metadata**: Informasi dasar tentang token
- **Graduation status**: Status kelulusan dari bonding curve

## 9. API Budget Tracking (Dari tabel `budget_ledger`)
- **API usage monitoring**: Penggunaan API per sumber
- **Rate limit tracking**: Pemantauan limit panggilan API
- **Cost management**: Pengelolaan biaya penggunaan API

## 10. Stale Positions (Dari berbagai tabel)
- **Stale position alerts**: Posisi yang terlalu lama terbuka
- **Aging analysis**: Analisis durasi posisi terbuka
- **Risk assessment**: Penilaian risiko posisi lama

## Prioritas Data

### Prioritas Tinggi:
1. **Equity Curve** - Kinerja keseluruhan sistem
2. **PnL Distribution** - Distribusi hasil trading
3. **Wallet Attribution** - Kinerja per wallet
4. **Daily Data Monitor** - Monitoring real-time
5. **Pipeline Metrics** - Metrik utama sistem

### Prioritas Sedang:
1. **Exit Reasons Analysis** - Pemahaman pola exit
2. **Strategy Performance** - Evaluasi hipotesis
3. **Open Positions** - Pemantauan posisi aktif
4. **Historical Charts** - Analisis harga

### Prioritas Rendah:
1. **Screening Effectiveness** - Validasi filter
2. **API Budget Tracking** - Operational monitoring
3. **Stale Position Alerts** - Risk management

## Format Data

### Time Series:
- Equity curve (cumulative PnL over time)
- Historical prices (OHLCV)
- Daily activity counts
- Moving averages

### Distribution:
- PnL buckets
- Exit reasons
- Win/loss ratios
- Performance percentiles

### Categorical:
- Wallet performance rankings
- Strategy effectiveness
- Token categories
- Data source metrics

### Real-time:
- Current open positions
- Recent trades
- Live data ingestion
- Alert status