import telebot
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from handlers import register_handlers

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("ОШИБКА: BOT_TOKEN не задан!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)
register_handlers(bot)

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()
print("Бот запущен и готов к работе!")
bot.infinity_polling()