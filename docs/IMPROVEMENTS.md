# Что изменено относительно VCa03 (2025)

Основание: статический разбор старого авторского bot.py. Старый проект не изменялся.

| Проблема | Изменение | Проверка |
|---|---|---|
| Новый поиск из inline-кнопки не переводил ConversationHandler в SEARCH_INPUT | Убран хрупкий автомат состояний: обычный текст всегда ищется | test_new_search_button_then_text |
| Пагинация/отмена удаления создавали DummyMsg без effective_user | Единый настоящий Update, владелец определяется из effective_user | test_favorites_pagination_regression, test_delete_cancel_and_confirm |
| requests.get внутри async без timeout блокировал event loop | Общий AsyncClient, 5с connect / 10с timeout, максимум 2 попытки | test_timeout_is_bounded |
| Сбой API выглядел как пустой поиск | Отдельные сообщения для отсутствия результатов и недоступности | test_api_failure_not_reported_as_empty |
| Прямая перезапись favorites.json, ошибки сохранения подавлялись | Транзакции SQLite, контроль ошибок, уникальная пара user/recipe | test_failed_storage_does_not_claim_success |
| Старые и повторные callback зависали | Немедленный answer, ID сессии поиска, понятный stale fallback | test_bad_or_legacy_callbacks |
| Полный ответ API и ID пользователей попадали в лог | Не логируются запросы/тела/ID; фильтр credential URL | test_logging_redacts_tokens |
| Сырые инструкции вставлялись в HTML, длинные тексты обрезались | Plain text, разбиение без потери текста, fallback без фото | test_long_text_and_missing_video |
| Избранное зависело от повторного lookup API | Локальный снимок ингредиентов/инструкции/ссылок | test_offline_saved_recipe_and_photo_failure |
| Изменить оценку после сохранения было неудобно | Повторная оценка и выделенная текущая звезда | test_rate_and_rerate_without_network |

## Границы улучшения

- Это переработанная реализация функционала прежнего проекта, а не обещание исправить API.
- Старый favorites.json не импортируется автоматически. В улучшенной версии отдельная база.
- Бот остаётся локальным учебным polling-приложением, не сервисом 24/7.
- Длинные рецепты отправляются несколькими сообщениями; кнопки оценки и видео — в конце.
- Ответы API не переводятся. Русский ввод сопровождается объяснением, а не ложным «ничего нет».
