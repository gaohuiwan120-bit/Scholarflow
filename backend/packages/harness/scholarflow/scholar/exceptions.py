"""ScholarFlow domain exceptions."""


class ScholarFlowError(Exception):
    """Base error for ScholarFlow modules."""


class ScholarValidationError(ScholarFlowError):
    """Raised when structured output fails schema validation."""


class ScholarPathError(ScholarFlowError):
    """Raised when a file path is outside allowed directories."""


class ScholarExternalServiceError(ScholarFlowError):
    """Raised when an external API (arXiv, GitHub) fails."""


class ScholarRateLimitError(ScholarExternalServiceError):
    """Raised when an external API rate-limits the client."""
