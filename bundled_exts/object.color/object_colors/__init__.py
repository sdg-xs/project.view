"""Object Colors for Kit. Core modules also run with standalone OpenUSD."""

try:
    import omni.ext
except ImportError:
    pass
else:
    from .extension import ObjectColorsExtension
