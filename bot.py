import telebot
import os
from handlers import register_handlers

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# Регистрируем все команды и кнопки
register_handlers(bot)

print("Бот запущен!")
bot.infinity_polling()