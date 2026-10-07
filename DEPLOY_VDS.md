# Инструкция по установке и запуску Discord Music Bot на VDS (Linux Ubuntu / Debian)

Данное руководство позволит развернуть бота на VDS сервере (например, в Аргентине, Нидерландах или Германии) для стабильной работы 24/7 без блокировок YouTube и задержек в Discord.

---

## 1. Подготовка системы и установка пакетов

Подключитесь к VDS по SSH (например: `ssh root@ip_сервера`) и выполните обновление пакетов:

```bash
sudo apt update && sudo apt upgrade -y
```

Установите необходимые системные утилиты:
- **Python 3 и venv**: для запуска виртуального окружения
- **FFmpeg**: для обработки и декодирования аудиопотоков
- **Git и curl**: для скачивания кода и утилит
- **Node.js**: необходим для `yt-dlp` (обход JavaScript-челленджей YouTube)
- **Компиляторы**: для сборки голосовых библиотек `pynacl`

```bash
# 1. Системные пакеты
sudo apt install -y python3 python3-pip python3-venv ffmpeg git curl build-essential libffi-dev

# 2. Установка Node.js (v20 LTS)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

Проверьте версии:
```bash
python3 --version
ffmpeg -version
node -v
```

---

## 2. Размещение кода бота

Создайте рабочую директорию и скопируйте файлы бота:

```bash
# Создаем папку для бота
mkdir -p /opt/discord-bot
cd /opt/discord-bot
```

> **Способы передачи файлов на сервер:**
> - Если код в вашем Git-репозитории: `git clone <ссылка_на_репо> /opt/discord-bot`
> - Или скопируйте файлы через SFTP/FileZilla / WinSCP с вашего ПК прямо в `/opt/discord-bot`.

---

## 3. Настройка виртуального окружения Python

В папке бота `/opt/discord-bot` создайте виртуальное окружение и установите библиотеки:

```bash
cd /opt/discord-bot

# Создаем изолированное окружение
python3 -m venv venv

# Активируем окружение
source venv/bin/activate

# Обновляем pip и ставим зависимости
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. Настройка файла конфигурации `.env`

Создайте файл `.env`:
```bash
nano .env
```

Вставьте ваши параметры (нажмите `Ctrl+O`, затем `Enter` для сохранения, `Ctrl+X` для выхода):
```dotenv
# Обязательный токен Discord бота
DISCORD_BOT_TOKEN=ваш_токен_бота_здесь

# Путь к FFmpeg (на Linux достаточно просто "ffmpeg")
FFMPEG_EXECUTABLE=ffmpeg

# Таймаут автоотключения при простое в секундах (300 = 5 минут, 0 = отключить)
IDLE_TIMEOUT=300

# Громкость по умолчанию (0.5 = 50%)
DEFAULT_VOLUME=0.5
```

---

## 5. Тестовый запуск

Запустите бота вручную для проверки:
```bash
source venv/bin/activate
python bot.py
```

Если в консоли появится:
```text
[INFO] Bot logged in as: ИмяБота#XXXX
[INFO] Successfully synced 9 slash commands.
```
значит всё настроено правильно! Остановите тестовый запуск сочетанием клавиш `Ctrl + C`.

---

## 6. Настройка автозапуска 24/7 (systemd service)

Чтобы бот работал в фоновом режиме, не выключался при закрытии SSH и автоматически поднимался при перезагрузке сервера, настроим службу `systemd`:

1. Создайте файл службы:
```bash
sudo nano /etc/systemd/system/discord-music-bot.service
```

2. Вставьте следующее содержимое:
```ini
[Unit]
Description=Discord Music Bot Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/discord-bot
ExecStart=/opt/discord-bot/venv/bin/python /opt/discord-bot/bot.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

3. Активируйте и запустите службу:
```bash
# Перечитываем конфигурацию systemd
sudo systemctl daemon-reload

# Включаем автозапуск при старте сервера
sudo systemctl enable discord-music-bot

# Запускаем бота
sudo systemctl start discord-music-bot
```

---

## 7. Управление ботом на сервере

- **Проверить статус работы:**
  ```bash
  sudo systemctl status discord-music-bot
  ```

- **Смотреть логи бота в реальном времени:**
  ```bash
  journalctl -u discord-music-bot -f
  ```

- **Перезапустить бота (например, после обновления кода):**
  ```bash
  sudo systemctl restart discord-music-bot
  ```

- **Остановить бота:**
  ```bash
  sudo systemctl stop discord-music-bot
  ```

---

## 8. Преимущества VDS за рубежом
1. **Никаких блокировок YouTube**: В отличие от серверов или ПК в РФ, зарубежный VDS имеет прямой скоростной доступ к CDN Google/YouTube без DNS-сбоев `getaddrinfo failed`.
2. **Низкий пинг**: Голосовые серверы Discord расположены в Европе (Амстердам, Франкфурт) — звук передается мгновенно без прерываний и задержек.
3. **24/7 доступность**: Музыка играет в канале независимо от включения или выключения вашего личного компьютера.
