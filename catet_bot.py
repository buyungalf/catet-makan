import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    MessageHandler,
    filters
)
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# File untuk menyimpan data
DATA_FILE = 'expense_data.csv'

# Konfigurasi Google Sheets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS = ServiceAccountCredentials.from_json_keyfile_name("google-sheets-key.json", SCOPE)
SHEET_ID = "1U-gDjDYfOmRN15OTRyggQ5Qff55IbqklqrtfakLPnVE"  # Ganti dengan ID spreadsheet Anda
SHEET_NAME = "Sheet1"       # Ganti jika nama sheet berbeda

# Inisialisasi file CSV jika belum ada
if not os.path.exists(DATA_FILE):
    df = pd.DataFrame(columns=['Tanggal', 'Jumlah', 'Keterangan'])
    df.to_csv(DATA_FILE, index=False)

# Command handlers
async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"Halo {user.first_name}! Saya adalah bot pencatat pengeluaran makan harian.\n\n"
        "Gunakan /catat untuk menambahkan pengeluaran makan hari ini.\n"
        "Gunakan /laporan untuk melihat laporan pengeluaran."
    )

async def catat_expense(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("Sarapan", callback_data='Sarapan')],
        [InlineKeyboardButton("Makan Siang", callback_data='Makan Siang')],
        [InlineKeyboardButton("Makan Malam", callback_data='Makan Malam')],
        [InlineKeyboardButton("Lainnya", callback_data='Lainnya')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Pilih jenis pengeluaran makan:', reply_markup=reply_markup)

async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    # Simpan pilihan user dalam context
    context.user_data['jenis_makanan'] = query.data
    
    await query.edit_message_text(text=f"Jenis: {query.data}\nSilakan kirim jumlah pengeluaran (contoh: 25000)")

async def save_expense(update: Update, context: CallbackContext):
    try:
        jumlah = float(update.message.text)
        jenis_makanan = context.user_data.get('jenis_makanan', 'Lainnya')
        tanggal = datetime.now().strftime('%Y-%m-%d')
        
        # Simpan ke Google Sheets
        save_to_sheets(tanggal, jumlah, jenis_makanan)
        
        await update.message.reply_text(f"✅ Pengeluaran {jenis_makanan} sebesar Rp{jumlah:,} berhasil dicatat di Google Sheets!")
        
    except ValueError:
        await update.message.reply_text("Format jumlah tidak valid. Silakan masukkan angka (contoh: 25000)")

async def laporan(update: Update, context: CallbackContext) -> None:
    try:
        df = pd.read_csv(DATA_FILE)
        
        if df.empty:
            await update.message.reply_text("Belum ada data pengeluaran yang tercatat.")
            return
            
        # Konversi kolom Tanggal ke datetime
        df['Tanggal'] = pd.to_datetime(df['Tanggal'])
        
        # Laporan hari ini
        today = datetime.now().strftime('%Y-%m-%d')
        today_expenses = df[df['Tanggal'] == today]
        
        # Laporan bulan ini
        current_month = datetime.now().strftime('%Y-%m')
        month_expenses = df[df['Tanggal'].dt.strftime('%Y-%m') == current_month]
        
        # Format pesan
        message = "📊 Laporan Pengeluaran Makan\n\n"
        message += f"📅 Hari ini ({today}):\n"
        message += f"Total: Rp{today_expenses['Jumlah'].sum():,}\n"
        message += f"Rata-rata: Rp{today_expenses['Jumlah'].mean():,.0f}\n\n"
        
        message += f"📅 Bulan ini ({current_month}):\n"
        message += f"Total: Rp{month_expenses['Jumlah'].sum():,}\n"
        message += f"Rata-rata per hari: Rp{month_expenses.groupby('Tanggal')['Jumlah'].sum().mean():,.0f}\n\n"
        
        # 5 pengeluaran terakhir
        message += "📝 5 Catatan Terakhir:\n"
        for _, row in df.tail(5).iterrows():
            message += f"- {row['Tanggal']}: Rp{row['Jumlah']:,} ({row['Keterangan']})\n"
        
        await update.message.reply_text(message)
        
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        await update.message.reply_text("Terjadi error saat membuat laporan.")

async def error_handler(update: object, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text('Maaf, terjadi error. Silakan coba lagi.')

def save_to_sheets(tanggal, jumlah, keterangan):
    try:
        client = gspread.authorize(CREDS)
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        sheet.append_row([tanggal, jumlah, keterangan])
    except Exception as e:
        logger.error(f"Gagal menyimpan ke Google Sheets: {e}")

def main() -> None:
    # Ganti dengan token bot Anda
    TOKEN = "7645553562:AAHU60kWa1Jy2zw9osl26OGpSSVWauZ1elU"
    
    # Buat Application dan tambahkan handlers
    application = Application.builder().token(TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("catat", catat_expense))
    application.add_handler(CommandHandler("laporan", laporan))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_expense))
    application.add_error_handler(error_handler)

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()