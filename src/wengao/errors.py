"""Protocol and transport failures with enough context for safe diagnostics."""


class WengaoError(Exception):
    """Base class for expected driver failures."""


class ConfigurationError(WengaoError):
    """A configuration value is invalid or unsafe."""


class ProtocolError(WengaoError):
    """A Modbus response is structurally invalid."""


class ResponseTimeoutError(ProtocolError):
    """The response did not arrive completely before the timeout."""

    def __init__(self, message: str, partial_response: bytes = b"") -> None:
        super().__init__(message)
        self.partial_response = partial_response


class CrcMismatchError(ProtocolError):
    """The received Modbus CRC does not match the frame."""


class UnexpectedResponseError(ProtocolError):
    """The response does not match the request."""


class ModbusExceptionResponseError(ProtocolError):
    """The device returned a Modbus exception response."""

    def __init__(self, function_code: int, exception_code: int) -> None:
        super().__init__(
            f"Modbus exception 0x{exception_code:02X} for function 0x{function_code:02X}"
        )
        self.function_code = function_code
        self.exception_code = exception_code


class UnsupportedDeviceError(ProtocolError):
    """The responder is not a recognised Wengao converter."""
