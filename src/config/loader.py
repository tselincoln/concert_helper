import yaml
from dataclasses import dataclass
from typing import List, Any


@dataclass
class Profile:
    name: str
    proxy_url: str
    phone_number: str
    # Add other attributes as needed by the system

    @classmethod
    def from_dict(cls, data: dict) -> 'Profile':
        return cls(
            name=data.get("name", "Unknown"),
            proxy_url=data.get("proxy_url", ""),
            phone_number=data.get("phone_number", ""),
        )


class ProfileLoader:
    """Handles loading and parsing of billing profiles from configuration files."""

    def __init__(self, config_path: str):
        self.config_path = config_path

    def load(self) -> List[Profile]:
        """Loads profiles from the specified YAML file."""
        try:
            with open(self.config_path, 'r') as f:
                data = yaml.safe_load(f)
            
            if not data or "profiles" not in data:
                return []

            return [Profile.from_dict(p) for p in data["profiles"]]
        except Exception as e:
            print(f"Error loading profiles: {e}")
            return []


def load_profiles(config_path: str) -> List[Profile]:
    """Convenience function to load profiles."""
    loader = ProfileLoader(config_path)
    return loader.load()
