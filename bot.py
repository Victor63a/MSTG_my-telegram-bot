import os
import re
import logging
from telegram import (
    Update,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
    ContextTypes,
    PicklePersistence
)
from dotenv import load_dotenv

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загружаем конфигурацию
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# Состояния диалога (добавлено SHOW_INSTRUCTIONS)
SHOW_INSTRUCTIONS, GET_NAME, CONFIRM_NAME, GET_SERVICES, GET_FORMAT, GET_CONTACT, CONFIRM_ORDER = range(7)

# Список услуг
SERVICES = [
    "Определение стратегии",
    "Создание канала",
    "Контент-план",
    "Написание постов",
    "Анализ публикаций"
]

# Список форматов оказания услуги
FORMATS = [
    "Консультация",
    "+ Разбор и инструкции",
    "+ Сопровождение 1 месяц"
]

async def cleanup_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, delete_user_msg=True):
    """Удаление предыдущих сообщений бота и пользователя"""
    if 'bot_messages' not in context.chat_data:
        context.chat_data['bot_messages'] = []
    
    # Удаляем предыдущие сообщения бота
    for msg_id in context.chat_data['bot_messages']:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение {msg_id}: {e}")
    
    # Очищаем список
    context.chat_data['bot_messages'] = []
    
    # Удаляем последнее сообщение пользователя (если нужно)
    if delete_user_msg and update.message:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение пользователя: {e}")

async def save_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, 
                      reply_markup=None, delete_user_msg=True, parse_mode=None):
    """Удаляет предыдущие сообщения и отправляет новое"""
    await cleanup_chat(update, context, delete_user_msg)
    message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )
    # Сохраняем ID нового сообщения
    if 'bot_messages' not in context.chat_data:
        context.chat_data['bot_messages'] = []
    context.chat_data['bot_messages'].append(message.message_id)
    return message

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога с показом инструкции"""
    # Очищаем предыдущие данные
    context.user_data.clear()
    context.chat_data.clear()
    
    # Проверяем, есть ли незавершенный диалог
    if context.user_data.get('in_conversation'):
        current_state = context.user_data.get('conversation_state', GET_NAME)
        return await continue_conversation(update, context, current_state)
    
    # Отправляем инструкцию
    instructions = (
        "📚 <b>Инструкция по работе с ботом</b>\n\n"
        "1. <b>Запуск</b>: нажмите /start или откройте диалог с ботом\n"
        "2. <b>Ввод данных</b>: укажите имя, выберите услуги и формат\n"
        "3. <b>Контактные данные</b>: телефон, email или Telegram-ник\n"
        "4. <b>Подтверждение</b>: проверьте и отправьте заявку\n\n"
        "🔹 <i>Все данные конфиденциальны</i>\n"
        "🔹 <i>Можно прервать диалог командой /cancel</i>\n\n"
        "Нажмите кнопку <b>Продолжить</b> чтобы начать👇"
    )
    
    keyboard = [[InlineKeyboardButton("➡️ Продолжить", callback_data="continue_to_start")]]
    
    await save_and_send(
        update, context,
        instructions,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
        delete_user_msg=False
    )
    return SHOW_INSTRUCTIONS

async def continue_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, state: int) -> int:
    """Продолжение незавершенного диалога"""
    if state == GET_NAME:
        return await send_greeting(update, context)
    elif state == GET_SERVICES:
        return await ask_services(update, context)
    elif state == GET_FORMAT:
        return await ask_format(update, context)
    elif state == GET_CONTACT:
        return await get_contact(update, context)
    elif state == CONFIRM_ORDER:
        return await confirm_order(update, context)
    else:
        return await send_greeting(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Основное меню после инструкции"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.delete_message()
    
    context.user_data['in_conversation'] = True
    context.user_data['conversation_state'] = GET_NAME
    return await send_greeting(update, context)

async def send_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Приветствие и запрос имени"""
    await save_and_send(
        update, context,
        "👋 Приветствую! Я помогу оформить заявку на услуги.\n\n"
        "Ответьте на 3 вопроса, и я всё оформлю.\n\n"
        "📌 Все данные конфиденциальны.\n\n"
        "Как Ваше имя?",
        reply_markup=ReplyKeyboardRemove()
    )
    return GET_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получаем имя пользователя с inline-кнопками"""
    context.user_data['conversation_state'] = GET_NAME
    user_input = update.message.text
    
    if len(user_input) < 3 or not re.match(r'^[a-zA-Zа-яА-ЯёЁ\s\-]+$', user_input):
        keyboard = [
            [InlineKeyboardButton("✅ Да, всё верно", callback_data="confirm_name_yes")],
            [InlineKeyboardButton("✏️ Исправить имя", callback_data="confirm_name_no")]
        ]
        
        await save_and_send(
            update, context,
            f"Вы уверены, что имя '{user_input}' написано правильно?",
            reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data['temp_name'] = user_input
        return CONFIRM_NAME
    
    context.user_data['name'] = user_input
    return await ask_services(update, context)

async def confirm_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка подтверждения имени через inline-кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_name_no":
        await save_and_send(update, context, "Напишите, пожалуйста, Ваше имя ещё раз:")
        return GET_NAME
    
    context.user_data['name'] = context.user_data['temp_name']
    context.user_data['conversation_state'] = GET_SERVICES
    await save_and_send(
        update, context,
        f"Принято, {context.user_data['name']}! Перейдём к выбору услуг.")
    return await ask_services(update, context)

async def ask_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос услуг с inline-кнопками"""
    context.user_data['conversation_state'] = GET_SERVICES
    if 'selected_services' not in context.user_data:
        context.user_data['selected_services'] = []
    
    keyboard = []
    for i, service in enumerate(SERVICES):
        prefix = "✅ " if service in context.user_data['selected_services'] else ""
        if i % 2 == 0:
            keyboard.append([InlineKeyboardButton(f"{prefix}{service}", callback_data=f"service_{i}")])
        else:
            keyboard[-1].append(InlineKeyboardButton(f"{prefix}{service}", callback_data=f"service_{i}"))
    
    keyboard.append([InlineKeyboardButton("➡️ Готово", callback_data="services_done")])
    
    text = (
        f"{context.user_data['name']}, выберите услуги:\n"
        "(можно выбрать несколько)\n\n"
        "и нажмите на кнопку Готово"
    )
    
    await save_and_send(
        update, context,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard))
    
    return GET_SERVICES

async def handle_service_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора услуги"""
    query = update.callback_query
    await query.answer()
    
    service_idx = int(query.data.split('_')[1])
    selected_service = SERVICES[service_idx]
    
    if selected_service in context.user_data['selected_services']:
        context.user_data['selected_services'].remove(selected_service)
    else:
        context.user_data['selected_services'].append(selected_service)
    
    return await ask_services(update, context)

async def handle_services_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение выбора услуг"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data['selected_services']:
        await query.answer("Выберите хотя бы одну услугу!", show_alert=True)
        return GET_SERVICES    
    context.user_data['service'] = ", ".join(context.user_data['selected_services'])
    context.user_data['conversation_state'] = GET_FORMAT
    return await ask_format(update, context)

async def ask_format(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос формата услуги"""
    context.user_data['conversation_state'] = GET_FORMAT
    keyboard = [
        [InlineKeyboardButton(FORMATS[0], callback_data="format_0")],
        [InlineKeyboardButton(FORMATS[1], callback_data="format_1")],
        [InlineKeyboardButton(FORMATS[2], callback_data="format_2")]
    ]
    
    await save_and_send(
        update, context,
        "Выберите формат сотрудничества:\n\n"
        "Консультация - бесплатная консультация,\n"
        "+ Разбор и инструкции - консультация, разбор канала и инструкции,\n"
        "+ Сопровождение 1 месяц - предыдущий пункт и сопровождение 1 месяц.",
        reply_markup=InlineKeyboardMarkup(keyboard))
    
    return GET_FORMAT

async def handle_format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора формата"""
    query = update.callback_query
    await query.answer()
    
    format_idx = int(query.data.split('_')[1])
    context.user_data['format'] = FORMATS[format_idx]
    context.user_data['conversation_state'] = GET_CONTACT
    
    await save_and_send(
        update, context,
        "📩 Как с Вами удобнее связаться?\n"
        "(телефон, email или Telegram username):",
        reply_markup=ReplyKeyboardRemove())
    
    return GET_CONTACT

async def get_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение контактных данных и показ предварительного просмотра заявки"""
    context.user_data['contact'] = update.message.text
    context.user_data['conversation_state'] = CONFIRM_ORDER
    
    # Формируем сообщение для предварительного просмотра
    preview_message = (
        "📋 Предварительный просмотр вашей заявки:\n\n"
        f"▪ Имя: {context.user_data['name']}\n"
        f"▪ Услуги: {context.user_data['service']}\n"
        f"▪ Формат: {context.user_data['format']}\n"
        f"▪ Контакты: {context.user_data['contact']}\n\n"
        "Проверьте правильность данных в заявке. Вы можете отправить Заявку или отменить её."
    )
    
    # Создаем клавиатуру с кнопками подтверждения
    keyboard = [
        [InlineKeyboardButton("✅ Отправить заявку", callback_data="submit_order")],
        [InlineKeyboardButton("❌ Отменить заявку", callback_data="cancel_order")]
    ]
    
    await save_and_send(
        update, context,
        preview_message,
        reply_markup=InlineKeyboardMarkup(keyboard))
    
    return CONFIRM_ORDER

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка подтверждения заявки (отдельная функция для продолжения диалога)"""
    return await handle_order_confirmation(update, context)

async def handle_order_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка подтверждения заявки"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_order":
        # Очищаем данные пользователя
        context.user_data.clear()
        context.chat_data.clear()
        
        # Отправляем сообщение об отмене
        await save_and_send(
            update, context,
            "❌ Заявка отменена. Все данные удалены.\n\n"
            "Чтобы начать новую заявку, нажмите /start",
            reply_markup=ReplyKeyboardRemove(),
            delete_user_msg=False)
        return ConversationHandler.END
    
    # Если пользователь подтвердил отправку
    try:
        # Формируем сообщение для пользователя
        user_message = (
            "📋 Ваша заявка:\n"
            f"▪ Имя: {context.user_data['name']}\n"
            f"▪ Услуги: {context.user_data['service']}\n"
            f"▪ Формат: {context.user_data['format']}\n"
            f"▪ Контакты: {context.user_data['contact']}\n\n"
            "✅ Заявка успешно отправлена!\n"
            "Я свяжусь с вами в течение 2 часов.\n\n"
            "Спасибо за обращение! 🤝"
        )
        
        # Формируем заявку для администратора
        admin_message = (
            "📌 Новая заявка:\n"
            f"👤 Имя: {context.user_data['name']}\n"
            f"🛠 Услуги: {context.user_data['service']}\n"
            f"📋 Формат: {context.user_data['format']}\n"
            f"📞 Контакты: {context.user_data['contact']}\n"
            f"🔗 Ссылка: [Написать](tg://user?id={update.effective_user.id})"
        )
        
        # Отправляем финальное сообщение пользователю
        await save_and_send(
            update, context,
            user_message,
            reply_markup=None,
            delete_user_msg=False)
        
        # Отправляем администратору
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_message,
            parse_mode="Markdown"
        )
        
        # Очищаем данные
        context.user_data.clear()
        context.chat_data.clear()
        
        return ConversationHandler.END
    
    except Exception as e:
        logger.error(f"Ошибка при обработке заявки: {e}")
        await save_and_send(
            update, context,
            "⚠️ Произошла ошибка при отправке заявки. Пожалуйста, попробуйте позже.",
            reply_markup=None)
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена диалога"""
    context.user_data.clear()
    context.chat_data.clear()
    await save_and_send(
        update, context,
        "Диалог прерван. Нажмите /start чтобы начать заново.",
        reply_markup=ReplyKeyboardRemove(),
        delete_user_msg=False)
    return ConversationHandler.END

def main() -> None:
    """Запуск бота"""
    try:
        logger.info("🟢 Запуск бота...")
        
        # Настройка сохранения состояния
        persistence = PicklePersistence(filepath='conversationbot.pickle')
        
        application = ApplicationBuilder() \
            .token(BOT_TOKEN) \
            .persistence(persistence) \
            .build()
        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                SHOW_INSTRUCTIONS: [CallbackQueryHandler(show_main_menu, pattern="^continue_to_start$")],
                GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
                CONFIRM_NAME: [CallbackQueryHandler(confirm_name, pattern="^confirm_name_")],
                GET_SERVICES: [
                    CallbackQueryHandler(handle_service_selection, pattern="^service_"),
                    CallbackQueryHandler(handle_services_done, pattern="^services_done$")
                ],
                GET_FORMAT: [CallbackQueryHandler(handle_format_selection, pattern="^format_")],
                GET_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_contact)],
                CONFIRM_ORDER: [CallbackQueryHandler(handle_order_confirmation, pattern="^(submit_order|cancel_order)$")],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            name="conversation_handler",
            persistent=True
        )
        
        application.add_handler(conv_handler)
        application.add_error_handler(lambda update, context: logger.error(f"Ошибка: {context.error}"))
        
        logger.info("🟢 Бот запущен и готов к работе")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"🔴 Ошибка запуска: {e}")
    finally:
        logger.info("🔴 Бот остановлен")

if __name__ == "__main__":
    main()