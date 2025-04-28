"""Environment variable management utility."""

import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class EnvManager:
    """Manages environment variables with type conversion and defaults."""
    @staticmethod
    def get_str(key: str, default: Optional[str] = None) -> Optional[str]:
        """Get string environment variable."""
        return os.getenv(key, default)

    @staticmethod
    def get_int(key: str, default: Optional[int] = None) -> Optional[int]:
        """Get integer environment variable."""
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            print(f"Warning: Environment variable {key} is not a valid integer. Using default: {default}")
            return default

    @staticmethod
    def get_float(key: str, default: Optional[float] = None) -> Optional[float]:
        """Get float environment variable."""
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            print(f"Warning: Environment variable {key} is not a valid float. Using default: {default}")
            return default

    @staticmethod
    def get_bool(key: str, default: Optional[bool] = None) -> Optional[bool]:
        """Get boolean environment variable."""
        value = os.getenv(key)
        if value is None:
            return default
        return value.lower() in ('true', 'yes', '1', 't', 'y')

    @staticmethod
    def get_list(key: str, default: Optional[List[str]] = None, delimiter: str = ',') -> Optional[List[str]]:
        """Get list environment variable (comma-separated by default)."""
        value = os.getenv(key)
        if value is None:
            return default or []
        return [item.strip() for item in value.split(delimiter) if item.strip()] 