from __future__ import annotations

from typing import Any

from telegram.ext import ContextTypes

from bookclub.config import CLUB_ENTITY
from bookclub.types import TranslationValue

T: dict[str, dict[str, TranslationValue]] = {
    "en": {
        "welcome": (
            "📚 <b>Welcome to the Book Club Bot!</b>\n\n"
            "➕ /add — Add a book\n"
            "📋 /list — See all books\n"
            "🏆 /top — Top rated books\n"
            "⚙️ /settings — Settings\n"
            "ℹ️ /info — About the bot\n"
            "✏️ /edit — Edit a book entry\n"
            "🗑 /delete — Delete a book\n"
            "✅ /discussed — Books already discussed\n"
            "🛠 /adminconsole — Admin console\n"
            "❓ /help — Show this message"
        ),
        "lang_set": "🇬🇧 Language set to English.",
        "ask_title": "📖 What is the <b>title</b> of the book?",
        "ask_author": "✍️ Who is the <b>author</b>?",
        "ask_pages": "📄 How many <b>pages</b> does it have? (enter a number)",
        "invalid_pages": "⚠️ Please enter a valid number of pages (e.g. 320):",
        "ask_fiction": "📂 Is it <b>Fiction</b> or <b>Non-fiction</b>?",
        "fiction_btn": "📖 Fiction",
        "nonfiction_btn": "📰 Non-fiction",
        "ask_review": "🔗 Paste the <b>link to a review</b> (must start with http:// or https://):",
        "invalid_review": "⚠️ That doesn't look like a valid URL. Please paste a link starting with http:// or https://:",
        "ask_original_language": "🌐 <b>Original language</b> of the book (or /skip if unsure):",
        "ask_creation_year": "📅 <b>Year of creation</b> (publication year; 4 digits, or /skip if unknown):",
        "invalid_creation_year": "⚠️ Please enter a valid 4-digit year (e.g. 1984), or /skip:",
        "ask_desc": "📝 Add a <b>description</b> (or /skip to leave empty):",
        "book_added": "✅ Book added!",
        "similar_title_warning": (
            "⚠️ A book with a <b>similar title</b> is already in the list:\n{matches}\n\n"
            "Continue adding <b>{title}</b>?"
        ),
        "similar_title_confirm_btn": "✅ Yes, continue",
        "similar_title_cancel_btn": "❌ No, cancel",
        "no_books": "📭 No books yet. Use /add to add one!",
        "no_undiscussed": "📭 No undiscussed books — use /discussed to see past reads.",
        "no_votes": "No votes yet. Use /list to see books and vote inline!",
        "no_books_edit": "📭 No books to edit yet.",
        "no_books_delete": "📭 No books to delete yet.",
        "cancelled": "❌ Cancelled.",
        "unexpected_error": "⚠️ Something went wrong on my side. Please try again — use /cancel first if you were in the middle of something.",
        "choose_vote": "📊 Choose a book to vote on:",
        "choose_edit": "✏️ Choose a book to edit:",
        "choose_delete": "🗑 Choose a book to delete:",
        "your_vote": "Your current vote",
        "none_vote": "—",
        "rate_book": "📊 Vote on <b>{title}</b>",
        "desc_updated": "✅ Description updated!",
        "top_title": "🏆 <b>Top Books</b>\nSorted by total score.\n",
        "added_by": "Added by",
        "added_on": "Added on",
        "pages_label": "Pages",
        "original_language_label": "Original language",
        "creation_year_label": "Year",
        "review_label": "Review",
        "cancel_btn": "❌ Cancel",
        "edit_field_prompt": "✏️ <b>{field}</b>\nCurrent value: <i>{value}</i>\n\nModify this field?",
        "edit_yes_btn": "✏️ Yes, change it",
        "edit_no_btn": "⏭ Skip",
        "edit_ask_new": "Send the new value for <b>{field}</b>:",
        "edit_done": "✅ Book updated!",
        "edit_invalid_pages": "⚠️ Must be a positive number. Send again:",
        "edit_invalid_url": "⚠️ Must start with http:// or https://. Send again:",
        "edit_invalid_creation_year": "⚠️ Must be a 4-digit year (e.g. 1984). Send again:",
        "field_title": "Title",
        "field_author": "Author",
        "field_pages": "Pages",
        "field_fiction": "Fiction / Non-fiction",
        "field_review": "Review link",
        "field_description": "Description",
        "field_original_language": "Original language",
        "field_creation_year": "Year of creation",
        "deleted": "🗑 <b>{title}</b> has been deleted.",
        "fiction_label": "Fiction",
        "nonfiction_label": "Non-fiction",
        "votes_label": lambda n: f"({n} vote{'s' if n != 1 else ''})",
        "want_label": "✅ want to read",
        "meh_label": "😐 don't care",
        "no_label": "❌ don't want to read",
        "vote_registered": "Your vote: {label}",
        "want_btn": "✅ Want",
        "meh_btn": "😐 Don't care",
        "no_btn": "❌ Don't want",
        "voted_msg": "✅ Vote saved for <b>{title}</b>",
        "score_label": "Score",
        "no_permission": "⛔ You can only edit or delete books you added.",
        "no_own_books": "📭 You have no books to edit or delete.",
        "admin_only": "⛔ This command is for admins only.",
        "admin_console_title": "🛠 <b>Admin Console</b>",
        "admin_mark_btn": "📌 Mark discussed",
        "admin_hide_btn": "👻 Hide book",
        "admin_notify_btn": "🔔 Send voting reminder (top)",
        "admin_notify_one_btn": "🔔 Send reminder for a specific book",
        "admin_notify_chat_btn": "💬 Post voting reminder to chat (top)",
        "admin_notify_chat_one_btn": "💬 Post reminder to chat (pick book)",
        "choose_notify_chat": "💬 Choose a book to post a voting reminder in the group chat:",
        "vote_reminder_chat": "🔔 <b>Voting reminder!</b>\n\n",
        "admin_notify_chat_confirm": "💬 Voting reminder posted to the group chat ({count} book(s)).",
        "admin_notify_chat_no_chat": "ℹ️ Group chat is not configured (ALLOWED_CHAT_ID).",
        "admin_notify_chat_failed": "⚠️ Failed to post to the group chat.",
        "admin_toggle_chat_btn": "💬 Post to chat: {state}",
        "admin_unhide_btn": "👁 Show book",
        "choose_hide": "👻 Choose a book to hide from the list:",
        "choose_unhide": "👁 Choose a hidden book to show again in the list:",
        "no_hidden": "📭 No hidden books.",
        "choose_notify": "🔔 Choose a book to send a reminder for:",
        "book_hidden": "✅ <b>{title}</b> is now hidden.",
        "book_unhidden": "✅ <b>{title}</b> is now visible.",
        "choose_mark": "📌 Choose a book to mark as discussed:",
        "admin_mark_menu": "📌 <b>Mark as discussed</b>\nWhat would you like to do?",
        "admin_mark_new_btn": "➕ Mark undiscussed as discussed",
        "admin_mark_edit_date_btn": "📅 Edit discussion date",
        "choose_edit_discuss_date": "📅 Choose a discussed book to change its discussion date:",
        "no_discussed_to_edit_date": "📭 No discussed books to edit.",
        "current_discussed_date": "Current date: <b>{date}</b>",
        "discussed_date_updated": "✅ Discussion date for <b>{title}</b> updated to {date}.",
        "no_unmark": "📭 No undiscussed books to mark.",
        "ask_discuss_date": "📅 Enter the <b>discussion date</b> (YYYY-MM-DD), or /today to use today:",
        "invalid_date": "⚠️ Invalid date. Use YYYY-MM-DD format (e.g. 2026-03-17):",
        "marked_discussed": "✅ <b>{title}</b> marked as discussed on {date}.",
        "discussed_title": "✅ <b>Discussed Books</b>\n\n",
        "no_discussed": "📭 No books have been discussed yet.",
        "discussed_on": "Discussed on",
        "list_prompt": "📋 <b>List of Books</b>\nShow all books or only those you haven't voted for yet?",
        "list_all_btn": "📚 All books",
        "list_unvoted_btn": "🗳 Unvoted only",
        "list_format_prompt": "📋 How would you like to view the list?",
        "list_compact_btn": "📄 Compact list",
        "list_full_btn": "📖 Full cards (vote inline)",
        "list_compact_title": "📋 <b>Books</b> ({count})\n",
        "score_calc_btn": "📊 How a score is calculated",
        "score_calc_info": "✅ Want: +1 point\n😐 Don't care: +0.5 points\n❌ Don't want: -1 point\nTotal score = sum of all votes (not average).Sorted by this score, then by date added.",
        "settings_title": "⚙️ <b>Settings</b>",
        "settings_notify_label": "Notifications for new books:",
        "settings_notify_on": "🔔 Enabled (5 min delay)",
        "settings_notify_off": "🔕 Disabled",
        "settings_notify_btn": "Toggle Notifications",
        "settings_lang_btn": "🌐 Switch to Russian",
        "notify_optin_prompt": "Would you like to receive notifications (with a 5-minute delay) when others add new books?",
        "notify_optin_yes": "🔔 Yes, notify me",
        "notify_optin_no": "🔕 No, thanks",
        "notify_optin_success": "✅ Settings saved!",
        "new_book_notification": "🆕 <b>New book added!</b>\n(Note: you receive this 5 minutes after it was added)\n\n",
        "new_book_delay_note": "\n\n<i>(Notifications for this book will be sent to others in 5 minutes)</i>",
        "not_member": "⛔ This bot is only for members of the <b>{chat}</b> chat. Please join first.",
        "bot_started": "🚀 <b>Bot is up!</b>",
        "bot_stopped": "🛑 <b>Bot is down.</b>",
        "admin_notify_confirm": "🔔 Voting reminder sent to {count} users.",
        "admin_notify_no_users": "ℹ️ No users to notify (everyone has voted or notifications disabled).",
        "vote_reminder_msg": "👋 <b>Friendly reminder!</b>\nYou haven't voted for some of our top books yet. Take a look and cast your vote:\n\n",
        "last_activity_label": "Last non-admin activity",
        "never": "never",
        "admin_export_btn": "📤 Export book (JSON)",
        "admin_import_btn": "📥 Import book (JSON)",
        "choose_export": "📤 Choose a book to export as JSON:",
        "export_done": "📤 Copy the JSON below and send it to another bot instance (Import in /adminconsole):\n\n<pre>{payload}</pre>",
        "import_prompt": "📥 Paste the book <b>JSON</b> from an export (one message). Votes are not included.\n\nSend /cancel to abort.",
        "import_done": "✅ Imported <b>{title}</b> (new id: {book_id}).",
        "import_invalid": "⚠️ Invalid import data. Expected JSON from 📤 Export book. Error: {error}",
        "import_entity_mismatch": "\n\n<i>Note: export was for “{exported}”, this bot uses “{local}”.</i>",
        "admin_meeting_create_btn": "📅 Record meeting attendance",
        "admin_meetings_view_btn": "👥 View meeting attendance",
        "choose_meeting_book": "📅 Choose the <b>discussed</b> book/film for this meeting:",
        "no_discussed_for_meeting": "📭 No discussed entries yet — mark one as discussed first.",
        "meeting_no_discussed_date": "⚠️ This entry has no discussion date — mark it as discussed with a date first.",
        "meeting_attendees_prompt": (
            "👥 <b>Who attended?</b> (discussion date: <b>{date}</b>)\n"
            "Tap names to toggle. Suggestions include voters and people who used the bot.\n"
            "Selected: <b>{count}</b>"
        ),
        "meeting_attendee_done_btn": "✅ Save meeting",
        "meeting_attendee_add_id_btn": "➕ Add by Telegram ID",
        "meeting_attendee_add_id_prompt": "Send the attendee's <b>numeric Telegram user ID</b> (or /cancel):",
        "meeting_attendee_invalid_id": "⚠️ Send a positive numeric Telegram user ID.",
        "meeting_attendee_added_id": "✅ Added user <code>{user_id}</code>.",
        "meeting_saved": "✅ Meeting saved for <b>{title}</b> on {date} — <b>{count}</b> attendee(s).",
        "no_meetings": "📭 No meetings recorded yet.",
        "choose_meeting_view": "👥 Choose a meeting to see who attended:",
        "meeting_view_title": "👥 <b>{title}</b>\n📅 Meeting: {date}\n\n<b>Attendees ({count}):</b>\n",
        "meeting_view_empty": "<i>No attendees recorded.</i>",
        "meeting_attendee_line": "• {name}",
        "bot_name": "Book Club Bot",
        "card_icon": "📖",
        "subtitle_icon": "✍️",
        "all_voted": "You've voted on all books!",
        "info_msg": (
            "🤖 <b>{bot_name}</b>\n\n"
            "📅 <b>Last update:</b> {last_commit}\n"
            "🔗 <b>Source code:</b> {github_repo}\n\n"
            "💬 Feel free to contact @antmaxi for suggestions on what to improve "
            "or if you run into issues with the bot."
        ),
    },
    "ru": {
        "welcome": (
            "📚 <b>Добро пожаловать в Книжный клуб!</b>\n\n"
            "➕ /add — Добавить книгу\n"
            "📋 /list — Список книг\n"
            "🏆 /top — Топ книг\n"
            "⚙️ /settings — Настройки\n"
            "ℹ️ /info — О боте\n"
            "✏️ /edit — Редактировать запись\n"
            "🗑 /delete — Удалить книгу\n"
            "✅ /discussed — Обсуждённые книги\n"
            "🛠 /adminconsole — Админ-панель\n"
            "❓ /help — Показать это сообщение"
        ),
        "lang_set": "🇷🇺 Язык установлен: Русский.",
        "ask_title": "📖 Как называется книга (<b>название</b>)?",
        "ask_author": "✍️ Кто <b>автор</b>?",
        "ask_pages": "📄 Сколько <b>страниц</b> в книге? (введите число)",
        "invalid_pages": "⚠️ Введите корректное число страниц (например, 320):",
        "ask_fiction": "📂 Это <b>художественная</b> или <b>нехудожественная</b> литература?",
        "fiction_btn": "📖 Худ. литература",
        "nonfiction_btn": "📰 Нехуд. литература",
        "ask_review": "🔗 Вставьте <b>ссылку на рецензию</b> (должна начинаться с http:// или https://):",
        "invalid_review": "⚠️ Это не похоже на корректный URL. Вставьте ссылку, начинающуюся с http:// или https://:",
        "ask_original_language": "🌐 <b>Язык оригинала</b> книги (или /skip, если не знаете):",
        "ask_creation_year": "📅 <b>Год создания</b> (год издания; 4 цифры, или /skip, если не знаете):",
        "invalid_creation_year": "⚠️ Введите корректный год из 4 цифр (например, 1984) или /skip:",
        "ask_desc": "📝 Добавьте <b>описание</b> (или /skip, чтобы пропустить):",
        "book_added": "✅ Книга добавлена!",
        "similar_title_warning": (
            "⚠️ В списке уже есть книга с <b>похожим названием</b>:\n{matches}\n\n"
            "Всё равно добавить <b>{title}</b>?"
        ),
        "similar_title_confirm_btn": "✅ Да, продолжить",
        "similar_title_cancel_btn": "❌ Нет, отмена",
        "no_books": "📭 Книг пока нет. Используйте /add, чтобы добавить!",
        "no_undiscussed": "📭 Необсуждённых книг нет — используйте /discussed для просмотра прочитанных.",
        "no_votes": "Голосов пока нет. Используйте /list для голосования!",
        "no_books_edit": "📭 Нет книг для редактирования.",
        "no_books_delete": "📭 Нет книг для удаления.",
        "cancelled": "❌ Отменено.",
        "unexpected_error": "⚠️ Что-то пошло не так с моей стороны. Попробуйте ещё раз — если вы были в середине команды, сначала используйте /cancel.",
        "choose_vote": "📊 Выберите книгу для голосования:",
        "choose_edit": "✏️ Выберите книгу для редактирования:",
        "choose_delete": "🗑 Выберите книгу для удаления:",
        "your_vote": "Ваш текущий голос",
        "none_vote": "—",
        "rate_book": "📊 Голосование: <b>{title}</b>",
        "desc_updated": "✅ Описание обновлено!",
        "top_title": "🏆 <b>Топ книг</b>\nСортировка по общему баллу.\n",
        "added_by": "Добавил",
        "added_on": "Добавлено",
        "pages_label": "Страниц",
        "original_language_label": "Язык оригинала",
        "creation_year_label": "Год",
        "review_label": "Рецензия",
        "cancel_btn": "❌ Отмена",
        "edit_field_prompt": "✏️ <b>{field}</b>\nТекущее значение: <i>{value}</i>\n\nИзменить это поле?",
        "edit_yes_btn": "✏️ Да, изменить",
        "edit_no_btn": "⏭ Пропустить",
        "edit_ask_new": "Отправьте новое значение для <b>{field}</b>:",
        "edit_done": "✅ Книга обновлена!",
        "edit_invalid_pages": "⚠️ Должно быть положительным числом. Отправьте снова:",
        "edit_invalid_url": "⚠️ Должна начинаться с http:// или https://. Отправьте снова:",
        "edit_invalid_creation_year": "⚠️ Должен быть год из 4 цифр (например, 1984). Отправьте снова:",
        "field_title": "Название",
        "field_author": "Автор",
        "field_pages": "Страниц",
        "field_fiction": "Fiction / Non-fiction",
        "field_review": "Ссылка на рецензию",
        "field_description": "Описание",
        "field_original_language": "Язык оригинала",
        "field_creation_year": "Год создания",
        "deleted": "🗑 <b>{title}</b> удалена.",
        "fiction_label": "Fiction",
        "nonfiction_label": "Non-fiction",
        "votes_label": lambda n: (
            f"({n} оценка)"
            if n == 1
            else f"({n} оценки)" if 2 <= n <= 4 else f"({n} оценок)"
        ),
        "want_label": "✅ хочу читать",
        "meh_label": "😐 всё равно",
        "no_label": "❌ не хочу читать",
        "vote_registered": "Ваш голос: {label}",
        "want_btn": "✅ Хочу",
        "meh_btn": "😐 Всё равно",
        "no_btn": "❌ Не хочу",
        "voted_msg": "✅ Голос сохранён для <b>{title}</b>",
        "score_label": "Балл",
        "no_permission": "⛔ Вы можете редактировать или удалять только добавленные вами книги.",
        "no_own_books": "📭 У вас нет книг для редактирования или удаления.",
        "admin_only": "⛔ Эта команда доступна только администраторам.",
        "admin_console_title": "🛠 <b>Админ-панель</b>",
        "admin_mark_btn": "📌 Отметить обсуждённой",
        "admin_hide_btn": "👻 Скрыть книгу",
        "admin_notify_btn": "🔔 Напомнить о голосовании (топ)",
        "admin_notify_one_btn": "🔔 Напомнить об одной книге",
        "admin_notify_chat_btn": "💬 Напомнить в чате (топ)",
        "admin_notify_chat_one_btn": "💬 Напомнить в чате (выбрать книгу)",
        "choose_notify_chat": "💬 Выберите книгу для напоминания о голосовании в общем чате:",
        "vote_reminder_chat": "🔔 <b>Напоминание о голосовании!</b>\n\n",
        "admin_notify_chat_confirm": "💬 Напоминание о голосовании отправлено в общий чат ({count} книг(и)).",
        "admin_notify_chat_no_chat": "ℹ️ Общий чат не настроен (ALLOWED_CHAT_ID).",
        "admin_notify_chat_failed": "⚠️ Не удалось отправить сообщение в общий чат.",
        "admin_toggle_chat_btn": "💬 Писать в чат: {state}",
        "admin_unhide_btn": "👁 Показать книгу",
        "choose_hide": "👻 Выберите книгу, чтобы скрыть её из списка:",
        "choose_unhide": "👁 Выберите скрытую книгу, чтобы снова показать её в списке:",
        "no_hidden": "📭 Нет скрытых книг.",
        "choose_notify": "🔔 Выберите книгу для напоминания:",
        "book_hidden": "✅ Книга <b>{title}</b> скрыта.",
        "book_unhidden": "✅ Книга <b>{title}</b> снова видна.",
        "choose_mark": "📌 Выберите книгу для отметки как обсуждённой:",
        "admin_mark_menu": "📌 <b>Отметить как обсуждённую</b>\nЧто сделать?",
        "admin_mark_new_btn": "➕ Отметить необсуждённую",
        "admin_mark_edit_date_btn": "📅 Изменить дату обсуждения",
        "choose_edit_discuss_date": "📅 Выберите обсуждённую книгу для изменения даты:",
        "no_discussed_to_edit_date": "📭 Нет обсуждённых книг для редактирования даты.",
        "current_discussed_date": "Текущая дата: <b>{date}</b>",
        "discussed_date_updated": "✅ Дата обсуждения для <b>{title}</b> изменена на {date}.",
        "no_unmark": "📭 Нет необсуждённых книг для отметки.",
        "ask_discuss_date": "📅 Введите <b>дату обсуждения</b> (ГГГГ-ММ-ДД) или /today для сегодняшней даты:",
        "invalid_date": "⚠️ Неверный формат даты. Используйте ГГГГ-ММ-ДД (например, 2026-03-17):",
        "marked_discussed": "✅ <b>{title}</b> отмечена как обсуждённая {date}.",
        "discussed_title": "✅ <b>Обсуждённые книги</b>\n\n",
        "no_discussed": "📭 Пока ни одна книга не была обсуждена.",
        "discussed_on": "Обсуждено",
        "list_prompt": "📋 <b>Список книг</b>\nПоказать все книги или только те, за которые вы ещё не голосовали?",
        "list_all_btn": "📚 Все книги",
        "list_unvoted_btn": "🗳 Только без моего голоса",
        "list_format_prompt": "📋 Как показать список?",
        "list_compact_btn": "📄 Краткий список",
        "list_full_btn": "📖 Полные карточки (голосование)",
        "list_compact_title": "📋 <b>Книги</b> ({count})\n",
        "score_calc_btn": "📊 Как рассчитывается балл",
        "score_calc_info": "✅ Хочу: +1 балл\n😐 Всё равно: +0.5 баллов\n❌ Не хочу: -1 балл\n\nСортировка по суммарному баллу, затем по дате добавления.",
        "settings_title": "⚙️ <b>Настройки</b>",
        "settings_notify_label": "Уведомления о новых книгах:",
        "settings_notify_on": "🔔 Включены (задержка 5 мин)",
        "settings_notify_off": "🔕 Выключены",
        "settings_notify_btn": "Переключить уведомления",
        "settings_lang_btn": "🌐 Switch to English",
        "notify_optin_prompt": "Хотите получать уведомления (с задержкой 5 минут), когда другие добавляют новые книги?",
        "notify_optin_yes": "🔔 Да, уведомлять",
        "notify_optin_no": "🔕 Нет, спасибо",
        "notify_optin_success": "✅ Настройки сохранены!",
        "new_book_notification": "🆕 <b>Добавлена новая книга!</b>\n(Примечание: вы получили это через 10 минут после добавления)\n\n",
        "new_book_delay_note": "\n\n<i>(Уведомления об этой книге будут разосланы остальным через 10 минут)</i>",
        "not_member": "⛔ Этот бот только для участников чата <b>{chat}</b>. Пожалуйста, сначала вступите в него.",
        "bot_started": "🚀 <b>Бот запущен!</b>",
        "bot_stopped": "🛑 <b>Бот остановлен.</b>",
        "admin_notify_confirm": "🔔 Напоминание о голосовании отправлено {count} пользователям.",
        "admin_notify_no_users": "ℹ️ Нет пользователей для уведомления (все проголосовали или уведомления отключены).",
        "vote_reminder_msg": "👋 <b>Напоминание!</b>\nВы еще не проголосовали за некоторые популярные книги. Посмотрите и оставьте свой голос:\n\n",
        "last_activity_label": "Последняя активность (не админ)",
        "never": "никогда",
        "admin_export_btn": "📤 Экспорт книги (JSON)",
        "admin_import_btn": "📥 Импорт книги (JSON)",
        "choose_export": "📤 Выберите книгу для экспорта в JSON:",
        "export_done": "📤 Скопируйте JSON и отправьте на другой инстанс бота (Импорт в /adminconsole):\n\n<pre>{payload}</pre>",
        "import_prompt": "📥 Вставьте <b>JSON</b> книги из экспорта (одним сообщением). Голоса не переносятся.\n\n/cancel — отмена.",
        "import_done": "✅ Импортировано: <b>{title}</b> (новый id: {book_id}).",
        "import_invalid": "⚠️ Неверные данные. Нужен JSON из 📤 Экспорт книги. Ошибка: {error}",
        "import_entity_mismatch": "\n\n<i>Экспорт для «{exported}», этот бот — «{local}».</i>",
        "admin_meeting_create_btn": "📅 Записать посещение встречи",
        "admin_meetings_view_btn": "👥 Кто был на встречах",
        "choose_meeting_book": "📅 Выберите <b>обсуждённую</b> книгу/фильм для этой встречи:",
        "no_discussed_for_meeting": "📭 Пока нет обсуждённых записей — сначала отметьте обсуждение.",
        "meeting_no_discussed_date": "⚠️ У записи нет даты обсуждения — сначала отметьте обсуждение с датой.",
        "meeting_attendees_prompt": (
            "👥 <b>Кто присутствовал?</b> (дата обсуждения: <b>{date}</b>)\n"
            "Нажимайте на имена, чтобы отметить. В списке — голосовавшие и пользовавшиеся ботом.\n"
            "Выбрано: <b>{count}</b>"
        ),
        "meeting_attendee_done_btn": "✅ Сохранить встречу",
        "meeting_attendee_add_id_btn": "➕ Добавить по Telegram ID",
        "meeting_attendee_add_id_prompt": "Отправьте <b>числовой Telegram user ID</b> участника (или /cancel):",
        "meeting_attendee_invalid_id": "⚠️ Нужен положительный числовой Telegram user ID.",
        "meeting_attendee_added_id": "✅ Добавлен пользователь <code>{user_id}</code>.",
        "meeting_saved": "✅ Встреча сохранена: <b>{title}</b>, {date} — <b>{count}</b> участник(ов).",
        "no_meetings": "📭 Встречи ещё не записывались.",
        "choose_meeting_view": "👥 Выберите встречу, чтобы увидеть участников:",
        "meeting_view_title": "👥 <b>{title}</b>\n📅 Встреча: {date}\n\n<b>Участники ({count}):</b>\n",
        "meeting_view_empty": "<i>Участники не указаны.</i>",
        "meeting_attendee_line": "• {name}",
        "bot_name": "Книжный клуб-бот",
        "card_icon": "📖",
        "subtitle_icon": "✍️",
        "all_voted": "Вы проголосовали за все книги!",
        "info_msg": (
            "🤖 <b>{bot_name}</b>\n\n"
            "📅 <b>Последнее обновление:</b> {last_commit}\n"
            "🔗 <b>Исходный код:</b> {github_repo}\n\n"
            "💬 Пишите @antmaxi с предложениями по улучшению бота или если что-то "
            "не работает."
        ),
    },
}

# Per-entity copy overrides (DB columns stay: author, pages, fiction).
ENTITY_STRING_OVERLAYS: dict[str, dict[str, dict[str, TranslationValue]]] = {
    "film": {
        "en": {
            "welcome": (
                "🎬 <b>Welcome to the Film Club Bot!</b>\n\n"
                "➕ /add — Add a film\n"
                "📋 /list — See all films\n"
                "🏆 /top — Top rated films\n"
                "⚙️ /settings — Settings\n"
                "ℹ️ /info — About the bot\n"
                "✏️ /edit — Edit a film entry\n"
                "🗑 /delete — Delete a film\n"
                "✅ /discussed — Films already discussed\n"
                "🛠 /adminconsole — Admin console\n"
                "❓ /help — Show this message"
            ),
            "bot_name": "Film Club Bot",
            "card_icon": "🎬",
            "subtitle_icon": "🎬",
            "ask_title": "🎬 What is the <b>title</b> of the film?",
            "ask_author": "🎬 Who is the <b>director</b>?",
            "ask_pages": "⏱ How long is it (<b>runtime in minutes</b>)? (enter a number)",
            "invalid_pages": "⚠️ Please enter a valid runtime in minutes (e.g. 120):",
            "ask_fiction": "📂 Is it a <b>feature film</b> or a <b>documentary</b>?",
            "ask_original_language": "🌐 <b>Original language</b> of the film (or /skip if unsure):",
            "ask_creation_year": "📅 <b>Release year</b> (4 digits, or /skip if unknown):",
            "fiction_btn": "🎬 Feature",
            "nonfiction_btn": "📽 Documentary",
            "book_added": "✅ Film added!",
            "similar_title_warning": (
                "⚠️ A film with a <b>similar title</b> is already in the list:\n{matches}\n\n"
                "Continue adding <b>{title}</b>?"
            ),
            "no_books": "📭 No films yet. Use /add to add one!",
            "no_undiscussed": "📭 No undiscussed films — use /discussed to see past picks.",
            "no_votes": "No votes yet. Use /list to see films and vote inline!",
            "no_books_edit": "📭 No films to edit yet.",
            "no_books_delete": "📭 No films to delete yet.",
            "choose_vote": "📊 Choose a film to vote on:",
            "choose_edit": "✏️ Choose a film to edit:",
            "choose_delete": "🗑 Choose a film to delete:",
            "rate_book": "📊 Vote on <b>{title}</b>",
            "top_title": "🏆 <b>Top Films</b>\nSorted by total score.\n",
            "pages_label": "min",
            "edit_done": "✅ Film updated!",
            "edit_invalid_pages": "⚠️ Must be a positive number of minutes. Send again:",
            "field_author": "Director",
            "field_pages": "Runtime (min)",
            "field_fiction": "Feature / Documentary",
            "field_creation_year": "Release year",
            "fiction_label": "Feature",
            "nonfiction_label": "Documentary",
            "want_label": "✅ want to watch",
            "no_label": "❌ don't want to watch",
            "no_permission": "⛔ You can only edit or delete films you added.",
            "no_own_books": "📭 You have no films to edit or delete.",
            "admin_hide_btn": "👻 Hide film",
            "admin_notify_one_btn": "🔔 Send reminder for a specific film",
            "admin_notify_chat_one_btn": "💬 Post reminder to chat (pick film)",
            "choose_notify_chat": "💬 Choose a film to post a voting reminder in the group chat:",
            "admin_unhide_btn": "👁 Show film",
            "choose_hide": "👻 Choose a film to hide from the list:",
            "choose_unhide": "👁 Choose a hidden film to show again in the list:",
            "choose_notify": "🔔 Choose a film to send a reminder for:",
            "choose_mark": "📌 Choose a film to mark as discussed:",
            "admin_mark_menu": "📌 <b>Mark as discussed</b>\nWhat would you like to do?",
            "admin_mark_new_btn": "➕ Mark undiscussed as discussed",
            "admin_mark_edit_date_btn": "📅 Edit discussion date",
            "choose_edit_discuss_date": "📅 Choose a discussed film to change its discussion date:",
            "no_discussed_to_edit_date": "📭 No discussed films to edit.",
            "current_discussed_date": "Current date: <b>{date}</b>",
            "discussed_date_updated": "✅ Discussion date for <b>{title}</b> updated to {date}.",
            "no_unmark": "📭 No undiscussed films to mark.",
            "marked_discussed": "✅ <b>{title}</b> marked as discussed on {date}.",
            "discussed_title": "✅ <b>Discussed Films</b>\n\n",
            "no_discussed": "📭 No films have been discussed yet.",
            "list_prompt": "📋 <b>List of Films</b>\nShow all films or only those you haven't voted for yet?",
            "list_all_btn": "🎬 All films",
            "list_compact_title": "📋 <b>Films</b> ({count})\n",
            "all_voted": "You've voted on all films!",
            "settings_notify_label": "Notifications for new films:",
            "notify_optin_prompt": "Would you like to receive notifications (with a 5-minute delay) when others add new films?",
            "new_book_notification": "🆕 <b>New film added!</b>\n(Note: you receive this 5 minutes after it was added)\n\n",
            "new_book_delay_note": "\n\n<i>(Notifications for this film will be sent to others in 5 minutes)</i>",
            "vote_reminder_msg": "👋 <b>Friendly reminder!</b>\nYou haven't voted for some of our top films yet. Take a look and cast your vote:\n\n",
            "admin_notify_chat_confirm": "💬 Voting reminder posted to the group chat ({count} film(s)).",
            "admin_export_btn": "📤 Export film (JSON)",
            "admin_import_btn": "📥 Import film (JSON)",
            "choose_export": "📤 Choose a film to export as JSON:",
        },
        "ru": {
            "welcome": (
                "🎬 <b>Добро пожаловать в Киноклуб!</b>\n\n"
                "➕ /add — Добавить фильм\n"
                "📋 /list — Список фильмов\n"
                "🏆 /top — Топ фильмов\n"
                "⚙️ /settings — Настройки\n"
                "ℹ️ /info — О боте\n"
                "✏️ /edit — Редактировать запись\n"
                "🗑 /delete — Удалить фильм\n"
                "✅ /discussed — Обсуждённые фильмы\n"
                "🛠 /adminconsole — Админ-панель\n"
                "❓ /help — Показать это сообщение"
            ),
            "bot_name": "Киноклуб-бот",
            "card_icon": "🎬",
            "subtitle_icon": "🎬",
            "ask_title": "🎬 Как называется <b>фильм</b> (название)?",
            "ask_author": "🎬 Кто <b>режиссёр</b>?",
            "ask_pages": "⏱ Сколько <b>минут</b> длится фильм? (введите число)",
            "invalid_pages": "⚠️ Введите корректную длительность в минутах (например, 120):",
            "ask_fiction": "📂 Это <b>художественный фильм</b> или <b>документальный</b>?",
            "ask_original_language": "🌐 <b>Язык оригинала</b> фильма (или /skip, если не знаете):",
            "ask_creation_year": "📅 <b>Год выхода</b> (4 цифры, или /skip, если не знаете):",
            "fiction_btn": "🎬 Худ. фильм",
            "nonfiction_btn": "📽 Документальный",
            "book_added": "✅ Фильм добавлен!",
            "similar_title_warning": (
                "⚠️ В списке уже есть фильм с <b>похожим названием</b>:\n{matches}\n\n"
                "Всё равно добавить <b>{title}</b>?"
            ),
            "no_books": "📭 Фильмов пока нет. Используйте /add, чтобы добавить!",
            "no_undiscussed": "📭 Необсуждённых фильмов нет — используйте /discussed для архива.",
            "no_votes": "Голосов пока нет. Используйте /list для голосования!",
            "no_books_edit": "📭 Нет фильмов для редактирования.",
            "no_books_delete": "📭 Нет фильмов для удаления.",
            "choose_vote": "📊 Выберите фильм для голосования:",
            "choose_edit": "✏️ Выберите фильм для редактирования:",
            "choose_delete": "🗑 Выберите фильм для удаления:",
            "rate_book": "📊 Голосование: <b>{title}</b>",
            "top_title": "🏆 <b>Топ фильмов</b>\nСортировка по общему баллу.\n",
            "pages_label": "мин",
            "edit_done": "✅ Фильм обновлён!",
            "edit_invalid_pages": "⚠️ Должно быть положительное число минут. Отправьте снова:",
            "field_author": "Режиссёр",
            "field_pages": "Длительность (мин)",
            "field_creation_year": "Год выхода",
            "field_fiction": "Худ. / документальный",
            "fiction_label": "Худ. фильм",
            "nonfiction_label": "Документальный",
            "want_label": "✅ хочу смотреть",
            "no_label": "❌ не хочу смотреть",
            "no_permission": "⛔ Вы можете редактировать или удалять только добавленные вами фильмы.",
            "no_own_books": "📭 У вас нет фильмов для редактирования или удаления.",
            "admin_hide_btn": "👻 Скрыть фильм",
            "admin_notify_one_btn": "🔔 Напомнить об одном фильме",
            "admin_notify_chat_one_btn": "💬 Напомнить в чате (выбрать фильм)",
            "choose_notify_chat": "💬 Выберите фильм для напоминания о голосовании в общем чате:",
            "admin_unhide_btn": "👁 Показать фильм",
            "choose_hide": "👻 Выберите фильм, чтобы скрыть его из списка:",
            "choose_unhide": "👁 Выберите скрытый фильм, чтобы снова показать его в списке:",
            "choose_notify": "🔔 Выберите фильм для напоминания:",
            "choose_mark": "📌 Выберите фильм для отметки как обсуждённого:",
            "admin_mark_menu": "📌 <b>Отметить как обсуждённый</b>\nЧто сделать?",
            "admin_mark_new_btn": "➕ Отметить необсуждённый",
            "admin_mark_edit_date_btn": "📅 Изменить дату обсуждения",
            "choose_edit_discuss_date": "📅 Выберите обсуждённый фильм для изменения даты:",
            "no_discussed_to_edit_date": "📭 Нет обсуждённых фильмов для редактирования даты.",
            "current_discussed_date": "Текущая дата: <b>{date}</b>",
            "discussed_date_updated": "✅ Дата обсуждения для <b>{title}</b> изменена на {date}.",
            "no_unmark": "📭 Нет необсуждённых фильмов для отметки.",
            "marked_discussed": "✅ <b>{title}</b> отмечен как обсуждённый {date}.",
            "discussed_title": "✅ <b>Обсуждённые фильмы</b>\n\n",
            "no_discussed": "📭 Пока ни один фильм не был обсуждён.",
            "list_prompt": "📋 <b>Список фильмов</b>\nПоказать все фильмы или только те, за которые вы ещё не голосовали?",
            "list_all_btn": "🎬 Все фильмы",
            "list_compact_title": "📋 <b>Фильмы</b> ({count})\n",
            "all_voted": "Вы проголосовали за все фильмы!",
            "settings_notify_label": "Уведомления о новых фильмах:",
            "notify_optin_prompt": "Хотите получать уведомления (с задержкой 5 минут), когда другие добавляют новые фильмы?",
            "new_book_notification": "🆕 <b>Добавлен новый фильм!</b>\n(Примечание: вы получили это через 10 минут после добавления)\n\n",
            "new_book_delay_note": "\n\n<i>(Уведомления об этом фильме будут разосланы остальным через 10 минут)</i>",
            "vote_reminder_msg": "👋 <b>Напоминание!</b>\nВы ещё не проголосовали за некоторые популярные фильмы. Посмотрите и оставьте свой голос:\n\n",
            "admin_notify_chat_confirm": "💬 Напоминание о голосовании отправлено в общий чат ({count} фильм(ов)).",
            "admin_export_btn": "📤 Экспорт фильма (JSON)",
            "admin_import_btn": "📥 Импорт фильма (JSON)",
            "choose_export": "📤 Выберите фильм для экспорта в JSON:",
        },
    },
}

_COMMAND_DESC_OVERLAYS: dict[str, dict[str, dict[str, str]]] = {
    "film": {
        "en": {
            "add": "➕ Add a film",
            "list": "📋 List films & vote inline",
            "top": "🏆 Top rated films",
            "discussed": "✅ Films already discussed",
            "edit": "✏️ Edit a film entry",
            "delete": "🗑 Delete a film",
        },
        "ru": {
            "add": "➕ Добавить фильм",
            "list": "📋 Список фильмов и голосование",
            "top": "🏆 Топ фильмов",
            "discussed": "✅ Обсуждённые фильмы",
            "edit": "✏️ Редактировать фильм",
            "delete": "🗑 Удалить фильм",
        },
    },
}


def _apply_entity_string_overlays(entity: str) -> None:
    for lang, keys in ENTITY_STRING_OVERLAYS.get(entity, {}).items():
        T[lang].update(keys)


_apply_entity_string_overlays(CLUB_ENTITY)

PM = "HTML"
def get_lang(ctx: ContextTypes.DEFAULT_TYPE) -> str:
    return str(ctx.user_data.get("lang", "ru"))


def tr(ctx_or_lang: ContextTypes.DEFAULT_TYPE | str, key: str, **kwargs: Any) -> str:
    lang = ctx_or_lang if isinstance(ctx_or_lang, str) else get_lang(ctx_or_lang)
    val = T[lang][key]
    if callable(val):
        result = val(**kwargs)
        return str(result)
    return val.format(**kwargs) if kwargs else str(val)


def s(lang: str, key: str) -> str:
    """Plain-string translation (not callable)."""
    val = T[lang][key]
    if not isinstance(val, str):
        raise TypeError(f"translation {key!r} is not a plain string")
    return val


_VOTE_LABEL_KEYS = {1: "want_label", 0: "meh_label", -1: "no_label"}


def vote_label_text(lang: str, score: int | None) -> str:
    if score not in _VOTE_LABEL_KEYS:
        raise ValueError(f"invalid vote score: {score!r}")
    return s(lang, _VOTE_LABEL_KEYS[score])

