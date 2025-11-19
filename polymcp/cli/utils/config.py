"""
Configuration Management
Handles loading, saving, and accessing configuration.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """
    Configuration manager for PolyMCP CLI.
    
    Manages configuration files with JSON format.
    Supports nested keys with dot notation (e.g., "llm.provider").
    """
    
    def __init__(self, config_dir: Path):
        """
        Initialize configuration manager.
        
        Args:
            config_dir: Directory containing config file
        """
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / 'polymcp_config.json'
        self._data: Dict = {}
        self._load()
    
    def _load(self) -> None:
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    self._data = json.load(f)
            except Exception as e:
                print(f"Warning: Could not load config: {e}")
                self._data = {}
        else:
            self._data = {}
    
    def _save(self) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.
        
        Args:
            key: Configuration key (supports dot notation)
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self._data
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value.
        
        Args:
            key: Configuration key (supports dot notation)
            value: Value to set
        """
        keys = key.split('.')
        data = self._data
        
        # Navigate to nested dict
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        
        # Set value
        data[keys[-1]] = value
        self._save()
    
    def delete(self, key: str) -> bool:
        """
        Delete configuration value.
        
        Args:
            key: Configuration key
            
        Returns:
            True if deleted, False if not found
        """
        keys = key.split('.')
        data = self._data
        
        # Navigate to parent dict
        for k in keys[:-1]:
            if k not in data:
                return False
            data = data[k]
        
        # Delete key
        if keys[-1] in data:
            del data[keys[-1]]
            self._save()
            return True
        
        return False
    
    def get_all(self) -> Dict:
        """
        Get all configuration.
        
        Returns:
            Complete configuration dictionary
        """
        return self._data.copy()
    
    def update(self, config: Dict) -> None:
        """
        Update configuration with dictionary.
        
        Args:
            config: Configuration dictionary to merge
        """
        self._data.update(config)
        self._save()
    
    def clear(self) -> None:
        """Clear all configuration."""
        self._data = {}
        self._save()
