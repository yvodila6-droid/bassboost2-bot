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
# 1. Обычный басбуст
EQ_FILTER_OLD = (
    "equalizer=f=50:t=q:w=1.5:g=20, "
    "equalizer=f=120:t=q:w=1.2:g=14, "
    "equalizer=f=250:t=q:w=1.2:g=-4, "
    "equalizer=f=4000:t=q:w=1.0:g=-3"
)

# 2. Анаболик (Идеален, не трогаем)
EQ_FILTER_ANABOLIC = (
    "equalizer=f=50:t=q:w=1.5:g=10, "
    "equalizer=f=120:t=q:w=1.2:g=6, "
    "equalizer=f=1000:t=q:w=1.0:g=8, "
    "equalizer=f=5000:t=q:w=1.0:g=8, "
    "asoftclip=type=hard:threshold=0.3, "
    "alimiter=limit=1.0"
)

# 3. CRUSH (Максимально похож на скрины: Distructor + Filter, БЕЗ РЕВЕРБА)
EQ_FILTER_CRUSH = (
    "equalizer=f=60:t=q:w=1.0:g=4, "       # Легкий саб
    "equalizer=f=200:t=q:w=1.0:g=-5, "     # Убираем бубнение
    "asoftclip=type=hard:threshold=0.05, " # Жесткий клиппинг (HARMOR CLASSIC, PRE AMP на максимум)
    "lowpass=f=3000, "                     # Фильтр (FILTER CUT), глухой звук
    "acrusher=level_in=1:level_out=1:bits=6:mode=log:aa=1, " # Ломает звук (6 бит - очень грязно)
    "alimiter=limit=1.0"
)

VOLUME_COMPRESSOR = "acompressor=threshold=0.9:ratio=5:attack=0.01:release=0.1:makeup=1.5"

def get_processing_filter(mode, bass_type, volume):
    if bass_type == "volume":
        return f"volume={volume / 100.0}, {VOLUME_COMPRESSOR}"
    
    if bass_type == "speed_only":
        if mode == "normal": return "anull"
        elif mode == "slowed": return "asetrate=44100*0.85,aresample=44100"
        elif mode == "speedup": return "asetrate=44100*1.15,aresample=44100"
        elif mode == "super_slowed": return "asetrate=44100*0.70,aresample=44100"
        elif mode == "super_speedup": return "asetrate=44100*1.35,aresample=44100"
    
    # Выбор баса
    if bass_type == "anabolic":
        base_filter = EQ_FILTER_ANABOLIC
    elif bass_type == "crush":
        base_filter = EQ_FILTER_CRUSH
    else:
        base_filter = EQ_FILTER_OLD
    
    # Скорости
    if mode == "normal": speed_filter = ""
    elif mode == "slowed": speed_filter = "asetrate=44100*0.85,aresample=44100,"
    elif mode == "speedup": speed_filter = "asetrate=44100*1.15,aresample=44100,"
    elif mode == "super_slowed": speed_filter = "asetrate=44100*0.70,aresample=44100,"
    elif mode == "super_speedup": speed_filter = "asetrate=44100*1.35,aresample=44100,"
        
    final = f"{base_filter}, volume={volume/100.0}, {VOLUME_COMPRESSOR}"
    if speed_filter:
        final = speed_filter + final
    return final

# --- ИНТЕРФЕЙС ---

def get_main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎵 Загрузить трек", callback_data="menu_process"),
        types.InlineKeyboardButton("⭐ Моё избранное", callback_data="menu_favs"),
        types.InlineKeyboardButton("🎚 Только громче", callback_data="preset_volume"),
        types.InlineKeyboardButton("⏱ Только скорость", callback_data="preset_speed")
    )
    return markup

def get_bass_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔥 Обычный басбуст", callback_data="bass_old"),
        types.InlineKeyboardButton("🧪 Anabolic", callback_data="bass_anabolic"),
        types.InlineKeyboardButton("💥 CRUSH (Broken Vinyl)", callback_data="bass_crush"),
        types.InlineKeyboardButton("🔊 Просто громче", callback_data="bass_volume"),
        types.InlineKeyboardButton("⏱ Только скорость", callback_data="bass_speed_only"),
        types.InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main")
    )
    return markup

def get_speed_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔥 Normal", callback_data="speed_normal"),
        types.InlineKeyboardButton("🐢 Slowed", callback_data="speed_slowed"),
        types.InlineKeyboardButton("🐇 Speed Up", callback_data="speed_speedup"),
        types.InlineKeyboardButton("🐌 Super Slowed", callback_data="speed_super_slowed"),
        types.InlineKeyboardButton("🚀 Super Speed Up", callback_data="speed_super_speedup"),
        types.InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main")
    )
    return markup


def register_handlers(bot):
    database.init_db()

    @bot.message_handler(commands=['start'])
    def start_message(message):
        bot.send_message(
            message.chat.id, 
            "Привет! 🎧 Я бот для создания мощных ремиксов.\n\n"
            "Выбери действие или просто отправь мне трек/видео!", 
            reply_markup=get_main_menu()
        )

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
    def back_to_main(call):
        bot.edit_message_text("Главное меню:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_main_menu())

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
        bot.edit_message_text("Просто отправь мне аудио или видео файл в чат!", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")))

    @bot.callback_query_handler(func=lambda call: call.data.startswith('preset_'))
    def handle_preset(call):
        preset = call.data.replace('preset_', '')
        chat_id = call.message.chat.id
        
        if preset == "volume":
            user_data[chat_id] = {"bass_type": "volume", "state": "waiting_volume"}
            bot.edit_message_text("🎚 Напиши уровень громкости от 0 до 1000:", chat_id=chat_id, message_id=call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")))
        elif preset == "speed":
            user_data[chat_id] = {"bass_type": "speed_only", "state": "waiting_speed"}
            bot.edit_message_text("⏱ Выбери скорость:", chat_id=chat_id, message_id=call.message.message_id, reply_markup=get_speed_menu())

    @bot.message_handler(content_types=['audio', 'document', 'voice', 'video'])
    def handle_media(message):
        file_info = None
        ext = ".mp3"
        is_video = False
        
        if message.audio:
            file_info = bot.get_file(message.audio.file_id)
        elif message.document and (message.document.mime_type.startswith('audio') or message.document.mime_type.startswith('video')):
            file_info = bot.get_file(message.document.file_id)
            ext = os.path.splitext(message.document.file_name)[1]
            if message.document.mime_type.startswith('video'): is_video = True
        elif message.voice:
            file_info = bot.get_file(message.voice.file_id)
            ext = ".ogg"
        elif message.video:
            file_info = bot.get_file(message.video.file_id)
            ext = ".mp4" 
            is_video = True
            
        if not file_info:
            bot.reply_to(message, "Пожалуйста, отправь аудио или видео.")
            return

        msg = bot.reply_to(message, "⏳ Скачиваю файл...")
        
        input_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}{ext}")
        downloaded_file = bot.download_file(file_info.file_path)
        with open(input_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        original_name = "Remix"
        if message.audio and message.audio.title:
            original_name = message.audio.title
        elif message.document and message.document.file_name:
            original_name = os.path.splitext(message.document.file_name)[0]
            
        user_data[message.chat.id] = {"path": input_path, "state": "waiting_bass_type", "name": original_name}
        
        text = "✅ Видео получено! (Звук будет извлечен)\n" if is_video else "✅ Файл получен!\n"
        bot.edit_message_text(text + "Выбери тип обработки:", chat_id=message.chat.id, message_id=msg.message_id, reply_markup=get_bass_menu())


    @bot.callback_query_handler(func=lambda call: call.data.startswith('bass_'))
    def handle_bass_choice(call):
        chat_id = call.message.chat.id
        bass_type = call.data.split('_')[1]
        
        user_data[chat_id]["bass_type"] = bass_type
        
        if bass_type in ["crush", "anabolic"]:
            user_data[chat_id]["volume"] = 100
            user_data[chat_id]["state"] = "waiting_speed"
            bot.edit_message_text(f"Выбран режим {bass_type.upper()}. Громкость зафиксирована (100).\nВыбери скорость:", chat_id=chat_id, message_id=call.message.message_id, reply_markup=get_speed_menu())
        elif bass_type == "speed_only":
            user_data[chat_id]["state"] = "waiting_speed"
            bot.edit_message_text("Выбран режим: только скорость.\nВыбери скорость:", chat_id=chat_id, message_id=call.message.message_id, reply_markup=get_speed_menu())
        else:
            user_data[chat_id]["state"] = "waiting_volume"
            bot.edit_message_text("🎚 Напиши уровень громкости от 0 до 1000:", chat_id=chat_id, message_id=call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")))


    @bot.message_handler(func=lambda message: message.text and message.text.strip().isdigit() and user_data.get(message.chat.id, {}).get("state") == "waiting_volume")
    def handle_volume(message):
        chat_id = message.chat.id
        volume = int(message.text.strip())
        if volume < 0 or volume > 1000:
            bot.reply_to(message, "⚠️ Введи число от 0 до 1000.")
            return
            
        user_data[chat_id]["volume"] = volume
        user_data[chat_id]["state"] = "waiting_speed"
        
        bot.reply_to(message, "✅ Громкость установлена.\nВыбери скорость:", reply_markup=get_speed_menu())


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
                mode_name = data['mode'].replace('_', ' ').title()
                
                if data['bass_type'] == "crush":
                    bass_name = "CRUSH"
                elif data['bass_type'] == "anabolic":
                    bass_name = "ANABOLIC"
                else:
                    bass_name = "BASS"
                    
                track_name = data['name']
                caption_text = f"🎵 {track_name}\n🔥 Стиль: {bass_name} | Скорость: {mode_name}"
                
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("⭐ В избранное", callback_data="fav_click"))
                markup.add(types.InlineKeyboardButton("🔄 Сделать ещё", callback_data="menu_process"))
                
                sent_msg = bot.send_audio(
                    chat_id, audio, 
                    caption=caption_text,
                    title=f"{bass_name} {track_name}",
                    performer="BassBoost Bot",
                    reply_markup=markup
                )
                
                database.add_to_favorites(chat_id, sent_msg.audio.file_id, caption_text)
                
        except subprocess.CalledProcessError as e:
            bot.send_message(chat_id, f"❌ Ошибка при обработке.")
            print(e.stderr.decode())
        finally:
            if os.path.exists(input_path): os.remove(input_path)
            if os.path.exists(output_path): os.remove(output_path)
            if chat_id in user_data: del user_data[chat_id]

    @bot.callback_query_handler(func=lambda call: call.data == "fav_click")
    def add_fav(call):
        bot.answer_callback_query(call.id, "⭐ Трек уже добавлен в избранное!")