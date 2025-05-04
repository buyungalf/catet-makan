#!/usr/bin/env python3

import os
from dotenv import load_dotenv

load_dotenv()

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    MessageHandler,
    filters,
    ConversationHandler
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pandas as pd

# Load environment variables


# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
GET_USERNAME = 1

# Konfigurasi Google Sheets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS = ServiceAccountCredentials.from_json_keyfile_dict({
    "type": os.getenv("GS_TYPE"),
    "project_id": os.getenv("GS_PROJECT_ID"),
    "private_key_id": os.getenv("GS_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GS_PRIVATE_KEY").replace('\\n', '\n'),
    "client_email": os.getenv("GS_CLIENT_EMAIL"),
    "client_id": os.getenv("GS_CLIENT_ID"),
    "auth_uri": os.getenv("GS_AUTH_URI"),
    "token_uri": os.getenv("GS_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("GS_AUTH_PROVIDER_CERT_URL"),
    "client_x509_cert_url": os.getenv("GS_CLIENT_CERT_URL")
}, SCOPE)
SHEET_ID = os.getenv("SHEET_ID")  # Get from environment variables
SHEET_NAME = "Sheet1"  # Ganti jika nama sheet berbeda

# Command handlers
async def start(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    await update.message.reply_text(
        f"Halo {user.first_name}! Saya adalah bot pencatat pengeluaran makan harian.\n\n"
        "Sebelum mulai, silakan masukkan username Anda:"
    )
    return GET_USERNAME

async def get_username(update: Update, context: CallbackContext) -> int:
    username = update.message.text
    context.user_data['username'] = username
    await update.message.reply_text(
        f"Username '{username}' berhasil disimpan!\n\n"
        "Gunakan /catat untuk menambahkan pengeluaran makan hari ini.\n"
        "Gunakan /laporan untuk melihat laporan pengeluaran."
    )
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text('Operasi dibatalkan.')
    return ConversationHandler.END

async def catat_expense(update: Update, context: CallbackContext) -> None:
    if 'username' not in context.user_data:
        await update.message.reply_text("Silakan set username Anda terlebih dahulu dengan /start")
        return
    
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
    if 'username' not in context.user_data:
        await update.message.reply_text("Silakan set username Anda terlebih dahulu dengan /start")
        return
    
    try:
        jumlah = float(update.message.text)
        jenis_makanan = context.user_data.get('jenis_makanan', 'Lainnya')
        tanggal = datetime.now().strftime('%Y-%m-%d')
        username = context.user_data['username']
        
        # Simpan ke Google Sheets
        save_to_sheets(tanggal, jumlah, jenis_makanan, username)
        
        await update.message.reply_text(f"✅ Pengeluaran {jenis_makanan} sebesar Rp{jumlah:,} berhasil dicatat di Google Sheets!")
        
    except ValueError:
        await update.message.reply_text("Format jumlah tidak valid. Silakan masukkan angka (contoh: 25000)")

async def laporan(update: Update, context: CallbackContext) -> None:
    if 'username' not in context.user_data:
        await update.message.reply_text("Silakan set username Anda terlebih dahulu dengan /start")
        return
    
    try:
        username = context.user_data['username']
        client = gspread.authorize(CREDS)
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        records = sheet.get_all_records()
        
        if not records:
            await update.message.reply_text("Belum ada data pengeluaran yang tercatat.")
            return
            
        # Filter data untuk user ini
        user_data = [row for row in records if row['User'] == username]
        
        if not user_data:
            await update.message.reply_text("Belum ada data pengeluaran yang tercatat untuk user Anda.")
            return
            
        # Konversi ke dataframe untuk pengolahan lebih mudah
        df = pd.DataFrame(user_data)
        df['Tanggal'] = pd.to_datetime(df['Tanggal'])
        
        # Laporan hari ini
        today = datetime.now().strftime('%Y-%m-%d')
        today_expenses = df[df['Tanggal'] == today]
        
        # Laporan bulan ini
        current_month = datetime.now().strftime('%Y-%m')
        month_expenses = df[df['Tanggal'].dt.strftime('%Y-%m') == current_month]
        
        # Format pesan
        message = f"📊 Laporan Pengeluaran Makan untuk {username}\n\n"
        message += f"📅 Hari ini ({today}):\n"
        message += f"Total: Rp{today_expenses['Jumlah'].sum():,}\n"
        if not today_expenses.empty:
            message += f"Rata-rata: Rp{today_expenses['Jumlah'].mean():,.0f}\n\n"
        
        message += f"📅 Bulan ini ({current_month}):\n"
        message += f"Total: Rp{month_expenses['Jumlah'].sum():,}\n"
        if not month_expenses.empty:
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

def save_to_sheets(tanggal, jumlah, keterangan, username):
    try:
        client = gspread.authorize(CREDS)
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        
        # Check if header exists, if not create it
        if not sheet.get_all_records():
            sheet.append_row(['Tanggal', 'Jumlah', 'Keterangan', 'User'])
            
        sheet.append_row([tanggal, jumlah, keterangan, username])
    except Exception as e:
        logger.error(f"Gagal menyimpan ke Google Sheets: {e}")

def main() -> None:
    # Get token from environment variables
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        return
    
    # Buat Application dan tambahkan handlers
    application = Application.builder().token(TOKEN).build()

    # Add conversation handler for username setup
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GET_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_username)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Register handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("catat", catat_expense))
    application.add_handler(CommandHandler("laporan", laporan))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_expense))
    application.add_error_handler(error_handler)

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()