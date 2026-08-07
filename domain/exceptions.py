"""Exception hierarchy shared by every domain module and Celery task.

Celery tasks distinguish these two families to decide whether to retry:
- TransientProviderError -> auto-retried (network blips, provider timeouts).
- PermanentPipelineError -> fails the pipeline immediately, no retry.
"""


class DomainError(Exception):
    """Base class for all errors raised from `domain/`."""


class TransientProviderError(DomainError):
    """Retryable failure: network error, provider timeout, rate limit, or a
    momentarily-unavailable local model server (e.g. Ollama still loading).
    """


class PermanentPipelineError(DomainError):
    """Non-retryable failure: corrupt/unsupported media, or a provider
    response that remains invalid after the allotted repair attempts.
    """


class UnsupportedMediaError(PermanentPipelineError):
    """Raised when ffprobe can't read the uploaded file at all."""


class ProviderResponseParseError(PermanentPipelineError):
    """Raised when an LLM provider's response can't be coerced into the
    expected schema even after a repair-prompt retry.
    """
