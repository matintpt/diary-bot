import os
import logging
import hashlib
import uuid
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)
from pymongo import MongoClient

# --- مراحل مکالمه
(REGISTER_PASS, LOGIN_PASS, ADD_TEXT, DELETE_SELECT, DELETE_ACCOUNT_CONFIRM, SEARCH_QUERY, EDIT_SELECT, EDIT_TEXT) = range(8)

# --- بارگذاری توکن و URI
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# --- اتصال به MongoDB Atlas
client = MongoClient(MONGO_URI)
db = client["diary_bot"]
users_col = db["users"]
sessions_col = db["sessions"]
diaries_col = db["diaries"]

# --- لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- هش کردن رمز عبور
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def is_logged_in(user_id):
    return sessions_col.find_one({"user_id": str(user_id), "logged_in": True}) is not None

# --- شروع
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📝 ثبت‌نام", callback_data='register')],
        [InlineKeyboardButton("🔐 ورود", callback_data='login')],
        [InlineKeyboardButton("➕ افزودن خاطره", callback_data='add')],
        [InlineKeyboardButton("📚 مشاهده خاطرات", callback_data='show')],
        [InlineKeyboardButton("🔍 جست‌وجو در خاطرات", callback_data='search')],
        [InlineKeyboardButton("❌ حذف خاطره", callback_data='delete')],
        [InlineKeyboardButton("✏️ ویرایش خاطره", callback_data='edit')],
        [InlineKeyboardButton("❌ حذف حساب کاربری", callback_data='delete_account')],
        [InlineKeyboardButton("🚪 خروج", callback_data='logout')],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("سلام! یکی از گزینه‌ها را انتخاب کنید:", reply_markup=markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text("سلام! یکی از گزینه‌ها را انتخاب کنید:", reply_markup=markup)

# --- دکمه‌ها
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    if query.data == 'register':
        await query.message.reply_text("لطفاً رمز عبور دلخواه خود را وارد کنید:")
        return REGISTER_PASS

    elif query.data == 'login':
        if is_logged_in(user_id):
            await query.message.reply_text("شما قبلاً وارد شده‌اید.")
            return ConversationHandler.END
        await query.message.reply_text("لطفاً رمز عبور خود را وارد کنید:")
        return LOGIN_PASS

    elif query.data == 'add':
        if not is_logged_in(user_id):
            await query.message.reply_text("❌ لطفاً ابتدا وارد شوید (/login).")
            return ConversationHandler.END
        await query.message.reply_text("لطفاً متن خاطره خود را ارسال کنید:")
        return ADD_TEXT

    elif query.data == 'show':
        if not is_logged_in(user_id):
            await query.message.reply_text("❌ لطفاً ابتدا وارد شوید (/login).")
        else:
            entries = list(diaries_col.find({"user_id": user_id}))
            if not entries:
                await query.message.reply_text("📭 هنوز خاطره‌ای ندارید.")
            else:
                messages = [f"{i+1}. {e['text']}" for i, e in enumerate(entries)]
                await query.message.reply_text("\n\n".join(messages))
        return ConversationHandler.END

    elif query.data == 'search':
        if not is_logged_in(user_id):
            await query.message.reply_text("❌ لطفاً ابتدا وارد شوید (/login).")
            return ConversationHandler.END
        await query.message.reply_text("🔍 لطفاً عبارت جست‌وجو را وارد کنید (حداقل ۳ حرف):")
        return SEARCH_QUERY

    elif query.data == 'delete':
        if not is_logged_in(user_id):
            await query.message.reply_text("❌ لطفاً ابتدا وارد شوید (/login).")
            return ConversationHandler.END
        entries = list(diaries_col.find({"user_id": user_id}))
        if not entries:
            await query.message.reply_text("📭 خاطره‌ای برای حذف وجود ندارد.")
            return ConversationHandler.END
        buttons = [
            [InlineKeyboardButton(f"حذف {i+1}. {e['text'][:20]}...", callback_data=f"del_{e['diary_id']}")]
            for i, e in enumerate(entries)
        ]
        buttons.append([InlineKeyboardButton("حذف همه خاطرات", callback_data="del_all")])
        await query.message.reply_text("کدام خاطره را می‌خواهید حذف کنید؟", reply_markup=InlineKeyboardMarkup(buttons))
        return DELETE_SELECT

    elif query.data == 'delete_account':
        if not is_logged_in(user_id):
            await query.message.reply_text("❌ لطفاً ابتدا وارد شوید (/login).")
            return ConversationHandler.END
        keyboard = [
            [InlineKeyboardButton("تأیید حذف حساب کاربری", callback_data="delete_account_confirm")],
            [InlineKeyboardButton("انصراف", callback_data="cancel_delete_account")]
        ]
        await query.message.edit_text("آیا مطمئنید که می‌خواهید حساب کاربری خود را حذف کنید؟", reply_markup=InlineKeyboardMarkup(keyboard))
        return DELETE_ACCOUNT_CONFIRM

    elif query.data == 'logout':
        sessions_col.delete_one({"user_id": user_id})
        await query.message.reply_text("🚪 با موفقیت از حساب خارج شدید.")
        return ConversationHandler.END

    elif query.data == 'edit':
        if not is_logged_in(user_id):
            await query.message.reply_text("❌ لطفاً ابتدا وارد شوید (/login).")
            return ConversationHandler.END
        entries = list(diaries_col.find({"user_id": user_id}))
        if not entries:
            await query.message.reply_text("📭 هنوز خاطره‌ای برای ویرایش وجود ندارد.")
            return ConversationHandler.END
        buttons = [
            [InlineKeyboardButton(f"{i+1}. {e['text'][:20]}...", callback_data=f"edit_{e['diary_id']}")]
            for i, e in enumerate(entries)
        ]
        await query.message.reply_text("کدام خاطره را می‌خواهید ویرایش کنید؟", reply_markup=InlineKeyboardMarkup(buttons))
        return EDIT_SELECT

    elif query.data.startswith("edit_"):
        context.user_data['edit_diary_id'] = query.data.replace("edit_", "")
        await query.message.reply_text("لطفاً متن جدید خاطره را ارسال کنید:")
        return EDIT_TEXT

async def register_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if users_col.find_one({"user_id": user_id}):
        await update.message.reply_text("شما قبلاً ثبت‌نام کرده‌اید.")
        return ConversationHandler.END
    password = hash_password(update.message.text)
    users_col.insert_one({"user_id": user_id, "password": password})
    await update.message.reply_text("✅ ثبت‌نام موفق بود.")
    return ConversationHandler.END

async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user = users_col.find_one({"user_id": user_id})
    if not user:
        await update.message.reply_text("ابتدا ثبت‌نام کنید.")
        return ConversationHandler.END
    if hash_password(update.message.text) == user["password"]:
        sessions_col.update_one({"user_id": user_id}, {"$set": {"logged_in": True}}, upsert=True)
        await update.message.reply_text("✅ وارد شدید!")
        return ConversationHandler.END
    await update.message.reply_text("❌ رمز اشتباه است.")
    return LOGIN_PASS

async def received_diary_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text
    diaries_col.insert_one({"user_id": user_id, "diary_id": str(uuid.uuid4()), "text": text})
    await update.message.reply_text("✅ خاطره ذخیره شد.")
    return ConversationHandler.END

async def search_diary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    query = update.message.text.strip()
    if len(query) < 3:
        await update.message.reply_text("🔎 حداقل ۳ حرف وارد کنید.")
        return SEARCH_QUERY
    results = diaries_col.find({"user_id": user_id, "text": {"$regex": query, "$options": "i"}})
    matches = [f"{i+1}. {e['text']}" for i, e in enumerate(results)]
    if matches:
        await update.message.reply_text("\n\n".join(matches))
    else:
        await update.message.reply_text("❌ موردی یافت نشد.")
    return SEARCH_QUERY

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    data = query.data

    if data == "del_all_confirm":
        diaries_col.delete_many({"user_id": user_id})
        await query.message.edit_text("✅ همه خاطرات حذف شدند.")
        return ConversationHandler.END

    elif data == "del_all":
        keyboard = [
            [InlineKeyboardButton("تأیید حذف همه", callback_data="del_all_confirm")],
            [InlineKeyboardButton("انصراف", callback_data="cancel_delete")]
        ]
        await query.message.edit_text("آیا مطمئنید؟", reply_markup=InlineKeyboardMarkup(keyboard))
        return DELETE_SELECT

    elif data.startswith("del_"):
        diary_id = data.replace("del_", "")
        diaries_col.delete_one({"user_id": user_id, "diary_id": diary_id})
        await query.message.edit_text("✅ خاطره حذف شد.")
        return ConversationHandler.END

    elif data == "delete_account_confirm":
        users_col.delete_one({"user_id": user_id})
        sessions_col.delete_one({"user_id": user_id})
        diaries_col.delete_many({"user_id": user_id})
        await query.message.edit_text("✅ حساب و خاطرات حذف شدند.")
        return ConversationHandler.END

    elif data in ["cancel_delete", "cancel_delete_account"]:
        await query.message.edit_text("❌ عملیات لغو شد.")
        return ConversationHandler.END

async def edit_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    new_text = update.message.text
    diary_id = context.user_data.get("edit_diary_id")
    if not diary_id:
        await update.message.reply_text("❌ خطا در ویرایش.")
        return ConversationHandler.END
    diaries_col.update_one({"user_id": user_id, "diary_id": diary_id}, {"$set": {"text": new_text}})
    await update.message.reply_text("✅ خاطره ویرایش شد.")
    return ConversationHandler.END

conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start), CallbackQueryHandler(button_handler)],
    states={
        REGISTER_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_password)],
        LOGIN_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)],
        ADD_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_diary_text)],
        DELETE_SELECT: [CallbackQueryHandler(confirm_delete, pattern="^del_.*|del_all|del_all_confirm|cancel_delete$")],
        DELETE_ACCOUNT_CONFIRM: [CallbackQueryHandler(confirm_delete, pattern="^delete_account_confirm|cancel_delete_account$")],
        SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_diary)],
        EDIT_SELECT: [CallbackQueryHandler(button_handler, pattern="^edit_.*")],
        EDIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_text_received)],
    },
    fallbacks=[],
)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('start', start))
    print("Bot is running...")
    app.run_polling()
