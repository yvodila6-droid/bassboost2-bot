import telebot
from telebot import types
import subprocess
import os
import uuid
import imageio_ffmpeg
import database

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
TEMP_DIR = "temp_audio"
os.makedirs(TEMP_DIR, exist_ok=True)

user_data = {}

# --- ФИЛЬТРЫ ---
# 1. Твой старый (обычный басбуст)
EQ_FILTER_OLD = (
    "equalizer=f=50:t=q:w=1.5:g=20, "
    "equalizer=f=120:t=q:w=1.2:g=14, "
    "equalizer=f=250:t=q:w=1.2:g=-4, "
    "equalizer=f=4000:t=q:w=1.0:g=-3"
)

# 2. Анаболик (Поднимаем ВСЁ, но добавляем жесткую сатурацию)
EQ_FILTER_ANABOLIC = (
    "equalizer=f=50:t=q:w=1.5:g=15, "   # Саб
    "equalizer=f=120:t=q:w=1.2:g=10, "  # Панч
    "equalizer=f=1000:t=q:w=1.0:g=8, "  # Поднимаем середину
    "equalizer=f=5000:t=q:w=1.0:g=8, "  # Поднимаем верх
    "asoftclip=type=hard:threshold=0.3, " # Жесткий клиппинг (шум)
    "alimiter=limit=1.0"
)

# 3. Общий компрессор для громкости (чтобы не душил бас)
VOLUME_COMPRESSOR = "acompressor=threshold=0.9:ratio=5:attack=0.01:release=0.1:makeup=1.5"

def get_processing_filter(mode, bass_type, volume):
    if bass_type == "volume":
        return f"volume={volume / 100.0}, {VOLUME_COMPRESSOR}"
    
    if bass_type == "anabolic":
        base_filter = EQ_FILTER_ANABOLIC
    else:
        base_filter = EQ_FILTER_OLD
    
    if mode == "normal":
        speed_filter = ""
    elif mode == "slowed":
        speed_filter = "asetrate=44100*0.85,aresample=44100,"
    elif mode == "speedup":
        speed_filter = "asetrate=44100*1.15,aresample=44100,"
    elif mode == "super_slowed":
        speed_filter = "asetrate=44100*0.70,aresample=44100,"
    elif mode == "super_speedup":
        speed_filter = "asetrate=44100*1.35,aresample=44100,"
        
    final = f"{base_filter}, volume={volume/100.0}, {VOLUME_COMPRESSOR}"
    if speed_filter:
        final = speed_filter + final
    return final


def register_handlers(bot):
    database.init_db()

    @bot.message_handler(commands=['start'])
    def start_message(message):
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🎵 Обработать трек", callback_data="menu_process"),
            types.InlineKeyboardButton("⭐ Избранные", callback_data="menu_favs")
        )
        bot.send_message(message.chat.id, "Привет! Я бот для ремиксов. Выбери действие:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "menu_favs")
    def show_favorites(call):
        favs = database.get_favorites(call.message.chat.id)
        if not favs:
            bot.answer_callback_query(call.id, "У тебя пока нет избранных треков.")
            return
        
        bot.answer_callback_query(call.id, "Загружаю...")
        for file_id, caption in favs:
            bot.send_audio(call.message.chat.id, file_id, caption=caption)

    @bot.callback_query_handler(func=lambda call: call.data == "menu_process")
    def process_menu(call):
        bot.edit_message_text("Просто отправь мне аудио или видео файл в чат!", chat_id=call.message.chat.id, message_id=call.message.message_id)

    @bot.message_handler(content_types=['audio', 'document', 'voice', 'video'])
    def handle_media(message):
        file_info = None
        ext = ".mp3"
        
        if message.audio:
            file_info = bot.get_file(message.audio.file_id)
        elif message.document and (message.document.mime_type.startswith('audio') or message.document.mime_type.startswith('video')):
            file_info = bot.get_file(message.document.file_id)
            ext = os.path.splitext(message.document.file_name)[1]
        elif message.voice:
            file_info = bot.get_file(message.voice.file_id)
            ext = ".ogg"
        elif message.video:
            file_info = bot.get_file(message.video.file_id)
            ext = ".mp4" 
            
        if not file_info:
            bot.reply_to(message, "Пожалуйста, отправь аудио или видео.")
            return

        msg = bot.reply_to(message, "⏳ Скачиваю файл...")
        
        input_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}{ext}")
        downloaded_file = bot.download_file(file_info.file_path)
        with open(input_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        user_data[message.chat.id] = {"path": input_path, "state": "waiting_bass_type"}
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🔥 Обычный басбуст", callback_data="bass_old"),
            types.InlineKeyboardButton("🧪 Анаболик (Шумно)", callback_data="bass_anabolic"),
            types.InlineKeyboardButton("🔊 Просто громче (Без баса)", callback_data="bass_volume")
        )
        bot.edit_message_text("✅ Файл получен!\nВыбери тип обработки:", chat_id=message.chat.id, message_id=msg.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('bass_'))
    def handle_bass_choice(call):
        chat_id = call.message.chat.id
        bass_type = call.data.split('_')[1]
        
        user_data[chat_id]["bass_type"] = bass_type
        user_data[chat_id]["state"] = "waiting_volume"
        
        bot.edit_message_text("🎚 Напиши уровень громкости от 0 до 1000 (100 — как в оригинале):", chat_id=chat_id, message_id=call.message.message_id)

    @bot.message_handler(func=lambda message: message.text and message.text.strip().isdigit() and user_data.get(message.chat.id, {}).get("state") == "waiting_volume")
    def handle_volume(message):
        chat_id = message.chat.id
        volume = int(message.text.strip())
        if volume < 0 or volume > 1000:
            bot.reply_to(message, "⚠️ Введи число от 0 до 1000.")
            return
            
        user_data[chat_id]["volume"] = volume
        
        if user_data[chat_id]["bass_type"] == "volume":
            user_data[chat_id]["mode"] = "volume_only"
            msg = bot.reply_to(message, "⚙️ Делаю трек громче... Это может занять пару секунд.")
            process_audio_now(chat_id, msg)
        else:
            user_data[chat_id]["state"] = "waiting_speed"
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("🔥 Normal", callback_data="speed_normal"),
                types.InlineKeyboardButton("🐢 Slowed", callback_data="speed_slowed"),
                types.InlineKeyboardButton("🐇 Speed Up", callback_data="speed_speedup"),
                types.InlineKeyboardButton("🐌 Super Slowed", callback_data="speed_super_slowed"),
                types.InlineKeyboardButton("🚀 Super Speed Up", callback_data="speed_super_speedup")
            )
            bot.reply_to(message, "✅ Громкость установлена.\nВыбери скорость:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('speed_'))
    def handle_speed_choice(call):
        chat_id = call.message.chat.id
        mode = call.data.split('_', 1)[1]
        user_data[chat_id]["mode"] = mode
        bot.edit_message_text(f"⚙️ Рендерю трек... Режим: {mode}. Пожалуйста, подожди.", chat_id=chat_id, message_id=call.message.message_id)
        process_audio_now(chat_id, call.message)

    def process_audio_now(chat_id, message):
        data = user_data.get(chat_id)
        if not data:
            return
            
        input_path = data["path"]
        output_path = os.path.join(TEMP_DIR, f"out_{uuid.uuid4()}.mp3")
        
        final_filter = get_processing_filter(data["mode"], data["bass_type"], data["volume"])
        
        command = [
            FFMPEG_PATH, '-y', '-i', input_path,
            '-af', final_filter,
            '-vn', '-b:a', '320k', output_path
        ]
        
        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            with open(output_path, 'rb') as audio:
                # Сохраняем трек в базу ДО отправки, чтобы получить короткий ID
                # Но так как мы не знаем file_id до отправки, отправим и сразу сохраним
                sent_msg = bot.send_audio(chat_id, audio, caption=f"Готово! 🎵\nРежим: {data['mode']}\nГромкость: {data['volume']}")
                
                # Сохраняем в базу и получаем ID записи
                db_id = database.add_to_favorites(chat_id, sent_msg.audio.file_id, "Избранный трек")
                
                # Кнопка с коротким ID (никаких file_id)
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("⭐ Добавить в избранное", callback_data=f"fav_{db_id}"))
                bot.edit_message_reply_markup(chat_id, sent_msg.message_id, reply_markup=markup)
                
        except subprocess.CalledProcessError as e:
            bot.send_message(chat_id, f"❌ Ошибка при обработке.")
            print(e.stderr.decode())
        finally:
            if os.path.exists(input_path): os.remove(input_path)
            if os.path.exists(output_path): os.remove(output_path)
            if chat_id in user_data: del user_data[chat_id]

    # Обработчик кнопки "Добавить в избранное"
    @bot.callback_query_handler(func=lambda call: call.data.startswith('fav_'))
    def add_fav(call):
        # ID записи, которую мы сохранили
        db_id = int(call.data.replace('fav_', ''))
        
        # Проверяем, есть ли такой трек в базе (он уже там, мы его сохранили при отправке)
        # Просто отвечаем пользователю, что всё ок
        bot.answer_callback_query(call.id, "⭐ Трек уже добавлен в избранное!")