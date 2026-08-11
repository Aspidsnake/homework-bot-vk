import json
import logging
import os
import random
import sys
import time
import traceback
import requests
import vk_api

from dotenv import load_dotenv

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
VK_TOKEN = os.getenv('VK_TOKEN')
VK_USER_ID = os.getenv('VK_USER_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

last_error_message_sent = None


def check_tokens():
    """Проверяет доступность всех обязательных переменных окружения."""
    missing = []
    if not PRACTICUM_TOKEN:
        missing.append('PRACTICUM_TOKEN')
    if not VK_TOKEN:
        missing.append('VK_TOKEN')
    if not VK_USER_ID:
        missing.append('VK_USER_ID')
    if missing:
        logging.critical(
            f'Отсутствует обязательная переменная окружения:\
                {", ".join(missing)}'
        )
        logging.critical('Программа принудительно остановлена.')
        sys.exit(1)


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API Практикума.
    В случае успеха возвращает ответ в виде Python-словаря.
    При ошибке соединения, неверном коде ответа или проблемах с JSON
    выбрасывает исключение ConnectionError или ValueError.
    """
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if response.status_code != 200:
            raise requests.exceptions.HTTPError(
                f'Эндпоинт {ENDPOINT} недоступен. Код ответа API: \
                    {response.status_code}'
            )
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f'Сбой при запросе к эндпоинту {ENDPOINT}: {e}')
        raise ConnectionError(f'Недоступность эндпоинта: {e}')
    except json.JSONDecodeError as e:
        logging.error(f'Некорректный JSON в ответе API: {e}')
        raise ValueError(f'Ошибка парсинга JSON: {e}')


def check_response(response):
    """Проверяет ответ API на соответствие ожидаемой структуре.
    Возвращает список домашних работ.
    """
    if not isinstance(response, dict):
        raise TypeError(f'Ответ API не является словарём. Получен тип \
                        {type(response)}')
    if 'homeworks' not in response or 'current_date' not in response:
        missing_keys = []
        if 'homeworks' not in response:
            missing_keys.append('homeworks')
        if 'current_date' not in response:
            missing_keys.append('current_date')
        logging.error(f'В ответе API отсутствуют обязательные ключи: \
                      {", ".join(missing_keys)}')
        raise KeyError(f'Обязательные ключи отсутствуют: {missing_keys}')
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        logging.error(f'Ключ "homeworks" должен быть списком. Получен тип \
                      {type(homeworks)}')
        raise TypeError('Поле homeworks не является списком')
    return homeworks


def parse_status(homework):
    """Извлекает статус конкретной домашней работы и формирует сообщение."""
    if 'homework_name' not in homework:
        raise KeyError('Отсутствует ключ "homework_name" \
                       в данных о домашней работе')
    homework_name = homework['homework_name']
    if 'status' not in homework:
        raise KeyError('Отсутствует ключ "status" в данных о домашней работе')
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        logging.error(f'Неожиданный статус работы "{homework_name}": {status}')
        raise ValueError(f'Неизвестный статус "{status}"')
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def send_message(vk, message):
    """Отправляет сообщение в VK чат, указанный в VK_USER_ID."""
    try:
        vk.messages.send(
            user_id=VK_USER_ID,
            message=message,
            random_id=random.randint(1, 2**31)
        )
        logging.debug(f'Бот отправил сообщение: "{message}"')
    except Exception as e:
        logging.error(f'Сбой при отправке сообщения в VK: {e}')
        raise


def main():
    """Основная логика работы бота."""
    global last_error_message_sent
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    check_tokens()
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    timestamp = 0
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                for homework in homeworks:
                    try:
                        message = parse_status(homework)
                        send_message(vk, message)
                    except Exception as e:
                        error_msg = f'Ошибка при обработке работы: {e}'
                        logging.error(error_msg)
                        if error_msg != last_error_message_sent:
                            try:
                                send_message(vk, error_msg)
                                last_error_message_sent = error_msg
                            except Exception:
                                logging.error('Не удалось отправить \
                                              сообщение об ошибке в VK')
            else:
                logging.debug('Новых статусов работ нет.')
            timestamp = response.get('current_date', int(time.time()))
        except Exception as error:
            full_error = f'Сбой в работе программы: {error}'
            logging.error(full_error)
            logging.debug(traceback.format_exc())
            if full_error != last_error_message_sent:
                try:
                    send_message(vk, full_error)
                    last_error_message_sent = full_error
                except Exception:
                    logging.error('Не удалось отправить \
                                  сообщение об ошибке в VK')
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
