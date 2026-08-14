class TokenMissingError(Exception):
    """Исключение для отсутствующих обязательных переменных окружения."""


class InvalidResponseCodeError(Exception):
    """Исключение для неверного кода ответа API."""
