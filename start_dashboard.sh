#!/bin/bash
# Skrip untuk menjalankan dashboard Theia dan verifikasi data

echo "🚀 Starting Theia Dashboard Setup..."
echo

# Cek apakah database ada
DB_PATH="/home/hermes/.hermes/theia/theia.db"
if [ ! -f "$DB_PATH" ]; then
    echo "❌ Database tidak ditemukan di $DB_PATH"
    echo "💡 Membuat direktori dan menyiapkan database..."
    mkdir -p /home/hermes/.hermes/theia/
    touch "$DB_PATH"
    echo "✅ Database placeholder dibuat"
fi

echo "📊 Memverifikasi struktur database..."
sqlite3 "$DB_PATH" ".tables" | head -10

echo
echo "📋 Memverifikasi data historis..."

# Cek jumlah data di tabel utama
echo "  - Archives (closed trades): $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM archives;" 2>/dev/null || echo 'Tidak ada')"
echo "  - Wallet profiles: $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM wallet_profiles;" 2>/dev/null || echo 'Tidak ada')" 
echo "  - Hypotheses: $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM hypotheses;" 2>/dev/null || echo 'Tidak ada')"
echo "  - Paper trades: $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM paper_trades;" 2>/dev/null || echo 'Tidak ada')"

echo
echo "🔧 Memastikan dependencies dashboard terinstal..."
cd /home/hermes/project-theia/dashboard/

# Cek apakah node_modules sudah ada
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dashboard dependencies..."
    npm install
else
    echo "✅ Dependencies sudah terinstal"
fi

echo
echo "🔍 Menyiapkan environment variables..."
ENV_FILE=".env.local"
if [ ! -f "$ENV_FILE" ]; then
    echo "THEIA_DB_PATH=/home/hermes/.hermes/theia/theia.db" > "$ENV_FILE"
    echo "NODE_ENV=development" >> "$ENV_FILE"
    echo "✅ Environment variables disiapkan"
else
    echo "✅ Environment variables sudah ada"
fi

echo
echo "✅ Semua siap untuk menjalankan dashboard!"
echo
echo "Berikut langkah-langkah selanjutnya:"
echo "1. Buka terminal baru dan jalankan: cd /home/hermes/project-theia && npm run dev"
echo "2. Buka browser dan akses: http://localhost:3000"
echo "3. Dashboard akan menampilkan data historis dari:"
echo "   - Closed trades (equity curve)"
echo "   - Wallet profiles (attribution)"  
echo "   - Hypotheses (strategy performance)"
echo "   - Exit reasons (performance analysis)"

echo
echo "💡 Tips: Jika ingin development, gunakan:"
echo "   - npm run dev (development mode)"
echo "   - npm run build && npm start (production mode)"