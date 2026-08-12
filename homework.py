import logging
import os
import random
import sys
import time
import traceback
from http import HTTPStatus

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


class TokenMissingError(Exception):
    """Исключение для отсутствующих обязательных переменных окружения."""

    pass


class InvalidResponseCodeError(Exception):
    """Исключение для неверного кода ответа API."""

    pass


def check_tokens():
    """Проверяет доступность всех обязательных переменных окружения."""
    tokens = (
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
        ('VK_TOKEN', VK_TOKEN),
        ('VK_USER_ID', VK_USER_ID)
    )
    missing_tokens = []
    for name, token in tokens:
        if not token:
            logging.critical(
                f'Отсутствует обязательная переменная окружения: {name}'
            )
            missing_tokens.append(name)
    if missing_tokens:
        raise TokenMissingError(
            f'Отсутствуют обязательные переменные окружения: '
            f'{", ".join(missing_tokens)}'
        )


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API Практикума.

    В случае успеха возвращает ответ в виде Python-словаря.
    При ошибке соединения, неверном коде ответа или проблемах с JSON
    выбрасывает исключение ConnectionError, InvalidResponseCodeError
    или ValueError.
    """
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp}
    }
    logging.info(
        f'Отправка запроса к API: url={request_params["url"]}, '
        f'headers={request_params["headers"]}, '
        f'params={request_params["params"]}'
    )
    try:
        response = requests.get(**request_params)
    except requests.exceptions.RequestException as e:
        raise ConnectionError(
            f'Недоступность эндпоинта '
            f'url={request_params["url"]}, '
            f'headers={request_params["headers"]}, '
            f'params={request_params["params"]}: {e}'
        )
    if response.status_code != HTTPStatus.OK:
        raise InvalidResponseCodeError(
            f'Неверный код ответа API: {response.status_code}. '
            f'Причина: {response.reason}. '
            f'Текст ответа: {response.text}'
        )
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие ожидаемой структуре.

    Возвращает список домашних работ.
    """
    if not isinstance(response, dict):
        raise TypeError(
            f'Ответ API не является словарём. '
            f'Получен тип {type(response)}'
        )
    if 'homeworks' not in response:
        raise KeyError('Ответ API не содержит обязательный ключ "homeworks"')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(
            f'Ключ "homeworks" должен быть списком. '
            f'Получен тип {type(homeworks)}'
        )
    return homeworks


def parse_status(homework):
    """Извлекает статус конкретной домашней работы и формирует сообщение."""
    if 'homework_name' not in homework:
        raise KeyError(
            'Отсутствует ключ "homework_name" в данных о домашней работе'
        )
    homework_name = homework['homework_name']
    if 'status' not in homework:
        raise KeyError(
            'Отсутствует ключ "status" в данных о домашней работе'
        )
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(
            f'Неожиданный статус работы "{homework_name}": {status}'
        )
    verdict = HOMEWORK_VERDICTS[status]
    return (
        f'Изменился статус проверки работы "{homework_name}". {verdict}'
    )


def send_message(vk, message):
    """Отправляет сообщение в VK чат, указанный в VK_USER_ID.

    Возвращает True при успешной отправке, иначе False.
    """
    try:
        vk.messages.send(
            user_id=VK_USER_ID,
            message=message,
            random_id=random.randint(1, 2**31)
        )
    except Exception:
        logging.error(
            f'Сбой при отправке сообщения в VK: {traceback.format_exc()}'
        )
        return False
    else:
        logging.debug(f'Бот отправил сообщение: "{message}"')
        return True


def _send_unique_message(vk, message, previous_message):
    """Отправляет сообщение, если оно не дублирует предыдущее.

    Возвращает обновлённое значение previous_message.
    """
    if message != previous_message:
        if send_message(vk, message):
            return message
    return previous_message


def main():
    """Основная логика работы бота."""
    logging.basicConfig(
        level=logging.DEBUG,
        format=(
            '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s'
        ),
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(__file__ + '.log', encoding='utf-8')
        ]
    )

    try:
        check_tokens()
    except TokenMissingError as e:
        logging.critical(str(e))
        sys.exit(1)

    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    timestamp = 0
    previous_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if not homeworks:
                logging.debug('Новых статусов работ нет.')
                continue
            homework = homeworks[0]
            current_message = parse_status(homework)
            previous_message = _send_unique_message(
                vk, current_message, previous_message
            )
            timestamp = response.get('current_date', int(time.time()))
        except Exception as error:
            current_error = f'Сбой в работе программы: {error}'
            logging.error(current_error)
            logging.debug(traceback.format_exc())
            previous_message = _send_unique_message(
                vk, current_error, previous_message
            )
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
