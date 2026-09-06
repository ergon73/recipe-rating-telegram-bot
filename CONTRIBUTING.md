# Разработка

1. Используйте Python 3.11–3.13 и отдельное виртуальное окружение.
2. Установите `requirements-dev.lock` с `--require-hashes`.
3. Установите проект: `python -m pip install --no-deps --no-build-isolation -e .`.
4. Перед PR выполните Ruff, pytest с покрытием и проверку зависимостей из README.
5. Для исправления ошибки сначала добавьте регрессионный тест.
6. Не используйте настоящий Telegram-токен, личные данные и сеть в unit-тестах.

## Обновление lock-файлов

В отдельном окружении с Python 3.12 установите `pip-tools==7.6.1`.
Затем, после проверки изменений в pyproject.toml:

```text
python -m piptools compile --generate-hashes --strip-extras --no-header -o requirements.lock pyproject.toml
python -m piptools compile --extra dev --allow-unsafe --generate-hashes --strip-extras --no-header -o requirements-dev.lock pyproject.toml
```

Просмотрите diff, проверьте `pip-audit`, unit-тесты и CI на Windows/Linux.
Сгенерированные lock-файлы не редактируйте вручную.

## Локальная особенность Windows

Если глобальный pytest temp недоступен, не меняйте права на чужие временные папки.
Укажите новый собственный каталог через `--basetemp`.
Для путей с кириллицей установите `PYTHONUTF8=1`.

## Публикация

`git diff --cached` → `python tools/check_public_tree.py` → commit → push.
Код и документация — в репозитории. Данные пользователей, секреты и тестовые базы — только локально.
