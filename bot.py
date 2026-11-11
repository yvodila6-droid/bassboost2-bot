import telebot
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from handlers import register_handlers

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("ОШИБКА: Переменная BOT_TOKEN не задана!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# Регистрируем все команды и кнопки из handlers.py
register_handlers(bot)

# --- ФЕЙКОВЫЙ САЙТ ДЛЯ RENDER (ЧТОБЫ ОН НЕ РУГАЛСЯ НА ПОРТЫ) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_server():
    # Render сам выдает нужный порт через переменную PORT
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# Запускаем сервер в отдельном потоке, чтобы он не блокировал бота
threading.Thread(target=run_health_server, daemon=True).start()

print("Бот запущен и готов к работе!")
bot.infinity_polling()