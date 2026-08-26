# ✅ Theia Dashboard - Siap untuk Menampilkan Data Historis

## Status Integrasi
Semua data historis dari Theia telah siap untuk ditampilkan di dashboard:

### 1. Data yang Sudah Tersedia
- **Closed Trades (6)**: Dari tabel `archives` - untuk equity curve dan PnL distribution
- **Wallet Profiles (116)**: Dari tabel `wallet_profiles` - untuk attribution analysis  
- **Hypotheses (3)**: Dari tabel `hypotheses` - untuk strategy performance
- **Open Positions**: Dari tabel `paper_trades` - untuk tracking posisi aktif
- **Token Data**: Dari tabel `tokens` - untuk reference informasi token

### 2. Struktur Database
- **Lokasi**: `/home/hermes/.hermes/theia/theia.db`
- **Mode Akses**: Read-only (seperti dikonfigurasi di `lib/db.ts`)
- **Tabel Utama**: `archives`, `wallet_profiles`, `hypotheses`, `paper_trades`, `tokens`

### 3. Komponen Dashboard yang Siap
- ✅ Equity Curve (dari closed trades)
- ✅ PnL Distribution (dari archives)
- ✅ Pipeline Metrics (jumlah wallets, posisi, dll)
- ✅ Wallet Attribution (performa per wallet)
- ✅ Strategy Performance (hypotheses testing)
- ✅ Exit Reasons Analysis (distribusi alasan exit)

## Cara Menjalankan Dashboard

### Development Mode:
```bash
cd /home/hermes/project-theia/dashboard
npm run dev
```
- Buka browser: http://localhost:3000
- Auto-refresh saat ada perubahan

### Production Mode:
```bash
cd /home/hermes/project-theia/dashboard
npm run build
npm start
```
- Buka browser: http://localhost:3000

## Data Historis yang Tersedia (per 23 Agustus 2026)

### Closed Trades Analysis:
- **Rentang waktu**: 18 Agustus - 22 Agustus 2026
- **Total trades**: 6
- **Sample hasil**: 
  - Mayoritas voided karena bug sol_usd (sudah diperbaiki)
  - Loss-making trades: -0.175 SOL rata-rata (hard stop losses)

### Wallet Profiling:
- **Total wallets tertrack**: 116
- **Wallet paling aktif**: 3dVxsdabRB... (421 trades)
- **Performa terbaik**: Win rate ~75.5%, Expectancy ~1.28 SOL

### Hypotheses Testing:
- **Aktif**: `hyp_wallet_cluster_latency` (Exp=0.015, PF=1.57, WR=62.5%)
- **Archived**: `hyp_swf_1786966826` (dead end)
- **Draft**: `hyp_postgrad_survival_v1` (belum diuji)

## Catatan Penting
- Database hanya bisa diakses read-only oleh dashboard (keamanan)
- Untuk historical charts, perlu mengisi `price_snapshots_v2` dengan OHLCV data
- Bug `sol_usd=0.0095` sudah diperbaiki di codebase (tidak akan terjadi lagi)
- Target: expectancy > 0 AND profit_factor > 1 (masih dalam pengujian)

## Troubleshooting
Jika dashboard tidak muncul:
1. Pastikan port 3000 tidak digunakan
2. Cek log: `cd /home/hermes/project-theia/dashboard && npm run dev`
3. Verifikasi database: `sqlite3 /home/hermes/.hermes/theia/theia.db ".tables"`