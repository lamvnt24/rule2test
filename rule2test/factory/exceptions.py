"""Stable application error vocabulary, independent of HTTP."""
class FactoryError(Exception):
    """Base error safe to translate at a transport boundary."""
class ValidationError(FactoryError, ValueError):
    """Input violates the domain contract."""
class ConfigurationError(FactoryError, ValueError):
    """Application configuration is invalid."""
class NotFoundError(FactoryError):
    """Referenced entity does not exist."""
class ConflictError(FactoryError):
    """Revision or state transition conflicts with persisted state."""
class ProviderError(FactoryError):
    """External provider failed."""
