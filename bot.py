import wikipedia
import logging
import os
import re
import requests
import json
import base64
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from datetime import datetime
import tempfile
from langdetect import detect, LangDetectException

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загружаем токены из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CLARIFAI_API_KEY = os.getenv("CLARIFAI_API_KEY")

if not TELEGRAM_TOKEN:
    logging.error("TELEGRAM_TOKEN не задан в переменных окружения")
    exit(1)

user_context = {}

RUSSIAN_TO_ENGLISH = {
    'хомяк': 'hamster', 'хомяки': 'hamsters',
    'ёжик': 'hedgehog', 'ежик': 'hedgehog', 'ежики': 'hedgehogs',
    'собака': 'dog', 'собаки': 'dogs',
    'кошка': 'cat', 'кошки': 'cats', 'кот': 'cat',
    'слон': 'elephant', 'слоны': 'elephants',
    'дельфин': 'dolphin', 'дельфины': 'dolphins',
    'лев': 'lion', 'львы': 'lions',
    'тигр': 'tiger', 'тигры': 'tigers',
    'птица': 'bird', 'птицы': 'birds',
    'рыба': 'fish',
    'черепаха': 'turtle', 'черепахи': 'turtles',
    'млекопитающее': 'mammal', 'млекопитающие': 'mammals',
    'ии': 'artificial intelligence',
    'искусственный интеллект': 'artificial intelligence',
}

RUSSIAN_DESCRIPTIONS = {
    'hamster': """Хомяк — небольшое млекопитающее из подсемейства хомяковых. Известны своими защечными мешками, в которых переносят пищу. Популярны в качестве домашних питомцев. Наиболее распространенный вид — сирийский хомяк. Активны в основном ночью.""",
    'hedgehog': """Ёжик (лат. Erinaceus) — млекопитающее из семейства ежовых. Известны своими иголками, которые на самом деле являются видоизмененными волосами. Питаются насекомыми, червями, иногда мелкими позвоночными и фруктами. Активны в основном ночью, на зиму впадают в спячку.""",
    'dog': """Собака (лат. Canis lupus familiaris) — домашнее животное, одно из наиболее популярных животных-компаньонов. Первое одомашненное животное, был одомашнен примерно 15 000 лет назад. Существует множество пород собак, которые различаются по размерам, масти, сложению и поведению.""",
    'cat': """Кошка (лат. Felis catus) — домашнее животное, одно из наиболее популярных «животных-компаньонов». Была одомашнена около 10 000 лет назад на Ближнем Востоке. Кошки являются хищниками и сохранили многие черты своих диких предков.""",
    'elephant': """Слон — самое крупное современное наземное животное. Отличается хоботом, бивнями и большими ушами. Существует три вида слонов: африканский саванный слон, африканский лесной слон и азиатский слон. Слоны живут семейными группами во главе со старшей самкой.""",
    'dolphin': """Дельфины — морские млекопитающие из отряда китообразных. Известны своим высоким интеллектом, игривым поведением и способностью к эхолокации. Спят дельфины особым образом: у них спит только одно полушарие мозга, чтобы они могли продолжать дышать и контролировать свое положение в воде.""",
    'lion': """Лев (лат. Panthera leo) — хищное млекопитающее рода пантер. Второй по величине после тигра представитель семейства кошачьих в мире. Единственные кошачьи, живущие в прайдах. Самцы отличаются гривой.""",
    'tiger': """Тигр (лат. Panthera tigris) — самый крупный и один из самых узнаваемых видов кошачьих. Отличается яркой оранжевой шерстью с черными полосами. Находится под угрозом исчезновения. Обитает в Азии.""",
    'mammal': """Млекопитающие — класс позвоночных животных, основной отличительной особенностью которых является вскармливание детёнышей молоком. Другие характерные черты: волосяной покров, теплокровность, наличие диафрагмы и развитой коры головного мозга.""",
    'artificial intelligence': """Искусственный интеллект (ИИ) — это технология создания компьютерных систем, способных выполнять задачи, требующие человеческого интеллекта: распознавание образов, принятие решений, обучение, понимание естественного языка. ИИ используется в медицине, транспорте, финансах и многих других областях.""",
    'question mark': """Вопросительный знак (?) — знак препинания, ставится обычно в конце предложения для выражения вопроса или сомнения. Встречается в печатных книгах с XVI века, однако для выражения вопроса он закрепляется значительно позже, лишь в XVIII веке.""",
}


def detect_language(text):
    """Определяет язык текста."""
    try:
        lang = detect(text)
        return 'ru' if lang == 'ru' else 'en'
    except LangDetectException:
        # fallback на регулярки
        ru_count = len(re.findall(r'[а-яА-ЯёЁ]', text))
        en_count = len(re.findall(r'[a-zA-Z]', text))
        return 'ru' if ru_count > en_count else 'en'

def extract_keyphrase(text, lang, user_id=None):
    """Извлекает ключевую фразу из текста."""
    text_lower = text.lower().strip()
    
    # Убираем вопросительный знак в конце 
    if text_lower.endswith('?') and 'вопросительный знак' not in text_lower:
        text_lower = text_lower.rstrip('?').strip()
    
    # Проверяем контекст пользователя для уточняющих вопросов
    if user_id and user_id in user_context:
        context = user_context[user_id]
        last_photo = context.get('last_photo_object')
        
        if last_photo:
            # Уточняющие вопросы о фото
            if any(word in text_lower for word in ['какое именно', 'какой именно', 'что именно', 'конкретно', 'точнее']):
                return f"specific:{last_photo}"
            
            if any(word in text_lower for word in ['какое это', 'что это за', 'это кто', 'кто это', 'а это']):
                return last_photo
    
    # Обработка времени
    time_pattern = r'\b\d{1,2}:\d{2}\b'
    if re.search(time_pattern, text):
        return "time"
    
    # Число 1617
    if re.search(r'\b1617\b', text):
        return "1617 number"
    
    # Вопросительный знак (явный запрос)
    if 'вопросительный знак' in text_lower or ('?' in text and 'что такое' in text_lower):
        return "question mark"
    
    # Вопросы о фото
    if any(x in text_lower for x in ['кто на фото', 'что на фото', 'что изображено']):
        return "photo question"
    
    # Простая логика для русского
    if lang == 'ru':
        # Сначала проверяем многословные фразы
        if 'как спят дельфины' in text_lower:
            return "dolphin sleep"
        
        # Затем отдельные слова
        words = text_lower.split()
        for word in words:
            if word in RUSSIAN_TO_ENGLISH:
                return RUSSIAN_TO_ENGLISH[word]
        
        # Проверка по подстроке
        if 'хомяк' in text_lower:
            return "hamster"
        elif 'ежик' in text_lower or 'ёжик' in text_lower:
            return "hedgehog"
        elif 'собака' in text_lower:
            return "dog"
        elif 'кошка' in text_lower or 'кот' in text_lower:
            return "cat"
        elif 'слон' in text_lower:
            return "elephant"
        elif 'дельфин' in text_lower:
            return "dolphin"
        elif 'лев' in text_lower:
            return "lion"
        elif 'тигр' in text_lower:
            return "tiger"
        elif 'млекопитающ' in text_lower:
            return "mammal"
        elif 'ии' in text_lower or 'искусственный интеллект' in text_lower:
            return "artificial intelligence"
    
    # Для английского
    else:
        if 'how do dolphins sleep' in text_lower or 'dolphins sleep' in text_lower:
            return "dolphin sleep"
        
        words = text_lower.split()
        for word in words:
            if word in ['hamster', 'hedgehog', 'dog', 'cat', 'elephant', 'dolphin', 'lion', 'tiger', 'mammal']:
                return word
        
        if 'artificial intelligence' in text_lower or ' ai ' in text_lower:
            return "artificial intelligence"
        elif 'question mark' in text_lower:
            return "question mark"
    
    return None

def search_wikipedia(query, lang='en'):
    """Ищет информацию в Википедии."""
    try:
        # Специальная обработка
        if query == "time":
            return f"Текущее время: {datetime.now().strftime('%H:%M')}"
        
        if query == "1617 number":
            return "1617 — натуральное число. 1617 год — невисокосный год, начинающийся в воскресенье по григорианскому календарю."
        
        if query == "photo question":
            return "Отправьте мне фото, и я проанализирую его содержимое с помощью компьютерного зрения."
        
        if query == "dolphin sleep":
            if lang == 'ru':
                return "Дельфины спят особым образом: у них спит только одно полушарие мозга, а второе бодрствует. Это позволяет им продолжать дышать и контролировать свое положение в воде. Такой сон называется однополушарным медленноволновым сном."
            else:
                return "Dolphins sleep with only one brain hemisphere at a time in slow-wave sleep. The other hemisphere remains awake to allow them to continue breathing and maintain awareness of their environment."
        
        # Для уточняющих вопросов о фото
        if query.startswith("specific:"):
            animal = query.split(":")[1]
            if animal == "mammal":
                return "По фото видно, что это млекопитающее. Для определения точного вида нужны более детальные признаки. Млекопитающие отличаются наличием шерсти, вскармливанием детенышей молоком и теплокровностью."
            elif animal in RUSSIAN_DESCRIPTIONS:
                return RUSSIAN_DESCRIPTIONS[animal]
            else:
                return f"На фото определен объект: '{animal}'. Это общая категория. Для более точной информации можно уточнить: 'Что это за {animal}?'"
        
        # Русские описания
        if lang == 'ru' and query in RUSSIAN_DESCRIPTIONS:
            return RUSSIAN_DESCRIPTIONS[query]
        
        # Для остальных запросов используем Wikipedia
        wikipedia.set_lang(lang)
        
        try:
            result = wikipedia.summary(query, sentences=3)
            return result
        except wikipedia.exceptions.DisambiguationError as e:
            if e.options:
                try:
                    result = wikipedia.summary(e.options[0], sentences=2)
                    return f"{result}\n\n(Также см. другие варианты)"
                except:
                    pass
            return f"Найдено несколько вариантов для '{query}'. Уточните запрос."
        except wikipedia.exceptions.PageError:
            return f"Информация по запросу '{query}' не найдена в Википедии."
            
    except Exception as e:
        logger.error(f"Ошибка Wikipedia: {e}")
        return "Произошла ошибка при поиске информации."

def analyze_image_clarifai(filename):
    """Анализирует изображение через Clarifai API."""
    try:
        if not os.path.exists(filename):
            return "Файл не найден", []
        
        with open(filename, 'rb') as f:
            image_data = f.read()
        
        api_key = CLARIFAI_API_KEY
        if not api_key:
            return "API ключ Clarifai не задан", []
        
        url = "https://api.clarifai.com/v2/models/general-image-recognition/versions/aa7f35c01e0642fda5cf400f543e7c40/outputs"
        
        headers = {
            "Authorization": f"Key {api_key}",
            "Content-Type": "application/json"
        }
        
        encoded_image = base64.b64encode(image_data).decode('utf-8')
        
        data = {
            "inputs": [
                {
                    "data": {
                        "image": {
                            "base64": encoded_image
                        }
                    }
                }
            ]
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            concepts = result['outputs'][0]['data']['concepts']
            
            # Фильтруем и сортируем по уверенности
            filtered_concepts = [c for c in concepts if c['value'] > 0.4]
            filtered_concepts.sort(key=lambda x: x['value'], reverse=True)
            
            if filtered_concepts:
                main_concept = filtered_concepts[0]['name'].lower()
                all_concepts = [c['name'].lower() for c in filtered_concepts[:5]]
                
                logger.info(f"Распознано: {main_concept} (другие: {all_concepts[1:]})")
                return main_concept, all_concepts
            else:
                return "неизвестный объект", []
                
        else:
            return f"ошибка {response.status_code}", []
            
    except Exception as e:
        logger.error(f"Ошибка анализа изображения: {e}")
        return "ошибка анализа", []


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    user_id = update.effective_user.id
    user_context[user_id] = {'last_photo_object': None, 'all_detected_objects': []}
    
    welcome_text = """
        
    📝 *Что умеет бот:*
    • Отвечать на вопросы о животных на русском и английском
    • Распознавать объекты на фотографиях
    • Поддерживать уточняющие вопросы
    • Рассказывать о ИИ, животных, технологиях
    
    🐹 *Примеры запросов (русский):*
    • Кто такие хомяки?
    • Расскажи о слонах
    • Как спят дельфины?
    • Что такое ИИ?
    • Что такое вопросительный знак?
    
    🐘 *Примеры запросов (английский):*
    • Tell me about elephants
    • What is artificial intelligence?
    • How do dolphins sleep?
    
    📷 *Отправьте фото* — бот распознает объекты на изображении
    
    🔍 *Уточняющие вопросы* после фото:
    • Какое именно это животное?
    • Что это за объект?
    • Расскажи подробнее
    
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')
    logger.info(f"Пользователь {user_id} начал диалог")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений."""
    user_id = update.effective_user.id
    user_text = update.message.text
    
    # Вывод в консоль
    print(f"ПОЛЬЗОВАТЕЛЬ [{user_id}]: {user_text}")
    print(f"Время: {datetime.now().strftime('%H:%M:%S')}")
    
    # Инициализируем контекст
    if user_id not in user_context:
        user_context[user_id] = {'last_photo_object': None, 'all_detected_objects': []}
    
    # Определяем язык
    lang = detect_language(user_text)
    print(f"Язык: {lang.upper()}")
    
    # Извлекаем ключевую фразу
    key_phrase = extract_keyphrase(user_text, lang, user_id)
    
    if not key_phrase:
        await update.message.reply_text("Не понял ваш запрос. Пожалуйста, уточните вопрос.")
        print(f"Не удалось извлечь ключевую фразу")
        return
    
    print(f"Ключевая фраза: '{key_phrase}'")
    
    # Обработка специальных случаев
    if key_phrase == "time":
        current_time = datetime.now().strftime("%H:%M")
        await update.message.reply_text(f"⏰ Текущее время: {current_time}")
        print(f"Ответ: {current_time}")
        return
    
    # Ищем информацию
    search_lang = 'ru' if lang == 'ru' else 'en'
    
    # Показываем что ищем
    search_indicator = f" *Ищу:* {key_phrase}"
    if key_phrase.startswith("specific:"):
        animal = key_phrase.split(":")[1]
        search_indicator = f" *Уточняю информацию о:* {animal}"
    
    await update.message.reply_text(search_indicator, parse_mode='Markdown')
    
    # Получаем результат
    result = search_wikipedia(key_phrase, search_lang)
    
    print(f" Результат: {result[:100]}...")
    
    await update.message.reply_text(result, parse_mode='Markdown')

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик фотографий."""
    user_id = update.effective_user.id
    
    print(f" ПОЛЬЗОВАТЕЛЬ [{user_id}]: отправил фото")
    print(f" Время: {datetime.now().strftime('%H:%M:%S')}")
    
    await update.message.reply_text("📸 *Анализирую изображение...*", parse_mode='Markdown')
    
    # Создаем временную папку в системной временной директории
    temp_dir = Path(tempfile.gettempdir()) / "bot_images"
    temp_dir.mkdir(exist_ok=True)
    
    try:
        # Скачиваем фото (самое большое)
        photo_file = await update.message.photo[-1].get_file()
        filename = temp_dir / f"photo_{user_id}_{datetime.now().strftime('%H%M%S')}.jpg"
        
        print(f" Скачиваю фото: {filename}")
        await photo_file.download_to_drive(filename)
        
        # Проверяем размер
        file_size = os.path.getsize(filename) / 1024
        print(f" Размер файла: {file_size:.1f} KB")
        
        # Анализируем изображение
        print(" Анализ через Clarifai...")
        main_object, all_objects = analyze_image_clarifai(str(filename))
        
        print(f" Распознано: {main_object}")
        if all_objects:
            print(f" Все объекты: {', '.join(all_objects)}")
        
        # Удаляем временный файл
        try:
            os.remove(filename)
            print(f" Файл удален")
        except:
            pass
        
        # Обрабатываем результат
        if main_object.startswith("ошибка"):
            await update.message.reply_text(f"❌ {main_object}")
            print(f" Ошибка распознавания")
            return
        
        if main_object == "неизвестный объект":
            await update.message.reply_text("🤔 Не удалось распознать объекты на фото. Попробуйте другое изображение с более четким объектом.")
            print(f"🤔 Неизвестный объект")
            return
        
        # Сохраняем контекст для уточняющих вопросов
        user_context[user_id]['last_photo_object'] = main_object
        user_context[user_id]['all_detected_objects'] = all_objects
        
        # Отвечаем на русском языке
        if main_object in RUSSIAN_DESCRIPTIONS:
            response_text = f" *На фото распознан:* {main_object}\n\n{RUSSIAN_DESCRIPTIONS[main_object]}"
        else:
            # Пробуем найти в Википедии на русском
            wikipedia.set_lang('ru')
            try:
                wiki_result = wikipedia.summary(main_object, sentences=2)
                response_text = f" *На фото распознан:* {main_object}\n\n{wiki_result}"
            except:
                # Если не нашли, даем общий ответ
                response_text = f" *На фото распознан:* {main_object}\n\nЭто объект категории '{main_object}'. Для получения подробной информации задайте уточняющий вопрос."
        
        # Добавляем информацию о других распознанных объектах
        if len(all_objects) > 1:
            other_objects = all_objects[1:min(4, len(all_objects))]
            response_text += f"\n\n *Также на фото:* {', '.join(other_objects)}"
        
        # Предлагаем уточняющие вопросы
        response_text += f"\n\n *Можно уточнить:*\n• «Какое именно это {main_object}?»\n• «Расскажи подробнее»\n• «Что это за {main_object}?»"
        
        print(f" Отправляю ответ")
        
        await update.message.reply_text(response_text, parse_mode='Markdown')
        
    except Exception as e:
        print(f" Ошибка: {e}")
        await update.message.reply_text(" Ошибка при обработке изображения")
        logger.error(f"Ошибка обработки фото: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок."""
    logger.error(f"Ошибка: {context.error}")
    
    if update and update.message:
        error_msg = str(context.error)[:100]
        await update.message.reply_text(f" Произошла ошибка: {error_msg}")


def main():
    """Запуск бота."""
    print("\n Журнал работы:")
    
    try:
        # Создаем приложение
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Регистрируем обработчики
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", start_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
        app.add_error_handler(error_handler)
        
        # Запускаем
        print(" Для остановки: Ctrl+C")
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        print(f"\n КРИТИЧЕСКАЯ ОШИБКА: {e}")

if __name__ == "__main__":
    main()
