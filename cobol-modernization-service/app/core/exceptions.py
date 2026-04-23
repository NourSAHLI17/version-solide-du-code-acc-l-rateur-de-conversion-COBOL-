"""Custom exceptions for the COBOL modernization pipeline."""


class PipelineError(Exception):
    """Raised on hard pipeline failures (e.g. circular COPY references).

    Attributes:
        errors: List of detailed error messages describing what went wrong.

    Example:
        Input:
            raise PipelineError("Circular COPY reference", ["Line 45: Circular COPY: DEFAULT/RECORDA"])
        Output:
            PipelineError with message "Circular COPY reference" and errors list
    """

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []
