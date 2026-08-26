# Data Historis Theia - Siap untuk Dashboard

## Ringkasan Data (per 23 Agustus 2026)

### 1. Closed Trades (Archives)
- **Total posisi tertutup**: 6
- **Rentang waktu**: 18 Agustus 2026 - 22 Agustus 2026
- **Sample hasil**:
  - PnL positif: 0 (karena kebanyakan voided karena bug sol_usd)
  - PnL negatif: -0.175 SOL rata-rata (hard stop losses)
  - Exit reason dominan: `voided_invalid_sol_usd` (bug), `hard_stop`

### 2. Open Positions (Paper Trades)
- **Total posisi terbuka**: 0
- Status: Semua posisi sudah ditutup/archive

### 3. Wallet Profiling
- **Total wallets tertrack**: 116
- **Wallet paling aktif**: 3dVxsdabRB... (421 trades)
- **Win rate tertinggi**: ~75.5% (wallet 3dVxsdabRB...)
- **Expectancy tertinggi**: ~1.28 SOL (wallet 3dVxsdabRB...)

### 4. Hypotheses Testing
- **Total strategi**: 3
- **Strategi aktif**: 
  - `hyp_wallet_cluster_latency`: Exp=0.015, PF=1.57, WR=62.5%
  - `hyp_postgrad_survival_v1`: Belum diuji (nilai None)
  - `hyp_swf_1786966826`: Sudah archived (dead end)

### 5. Token Tracking
- **Total tokens**: 86
- **Price snapshots**: 0 (belum diisi, bisa digunakan untuk historical charts)

## Integrasi ke Dashboard

### Komponen yang Sudah Siap:
- ✅ **Equity Curve**: Dari archives (6 closed trades)
- ✅ **PnL Distribution**: Dari archives (bucket >5x, 2x-5x, dll)
- ✅ **Pipeline Metrics**: Tracked wallets (116), closed positions (6)
- ✅ **Wallet Attribution**: Dari wallet_profiles (116 wallets)
- ✅ **Exit Reasons**: Dari archives (hard_stop, voided_invalid_sol_usd)
- ❌ **Historical Charts**: Price snapshots kosong (akan diisi nanti)

### Lokasi Database:
- Path: `/home/hermes/.hermes/theia/theia.db`
- Tables: archives, paper_trades, wallet_profiles, hypotheses, tokens
- Access: Read-only via dashboard (seperti di `lib/db.ts`)

## Rekomendasi Selanjutnya:
1. Jalankan dashboard: `cd /home/hermes/project-theia && npm run dev`
2. Dashboard akan otomatis membaca semua data di atas
3. Untuk historical charts, perlu isi price_snapshots_v2 dengan OHLCV data
4. Monitor kinerja hypothesis `hyp_wallet_cluster_latency` yang sedang diuji

## Catatan Penting:
- Ada bug `sol_usd=0.0095` yang menyebabkan banyak trade voided (sudah di-fix di codebase)
- Strategi saat ini masih dalam fase backtesting/paper trading
- Target: expectancy > 0 AND profit_factor > 1 (belum tercapai)