"""Typed errors for the Beatitude Engine."""


class BeatitudeError(Exception):
    """Base class for all engine errors."""


class ConfigError(BeatitudeError):
    """A required environment variable or file is missing or invalid."""


class ReviewerError(BeatitudeError):
    """A model reviewer call failed or returned unusable output."""


class StoreError(BeatitudeError):
    """A Supabase read or write failed."""


class SealRefused(BeatitudeError):
    """issue_seal() refused: the required verdict or human sign-off is missing."""
