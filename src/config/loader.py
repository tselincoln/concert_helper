import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Profile:
    name: str
    proxy_url: str
    phone_number: str
    billing: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> 'Profile':
        billing_raw = data.get("billing", {})
        return cls(
            name=data.get("name", "Unknown"),
            proxy_url=data.get("proxy_url", ""),
            phone_number=data.get("phone_number",
                                  billing_raw.get("phone", "")),
            billing={
                "name":        billing_raw.get("name", ""),
                "email":       billing_raw.get("email", ""),
                "phone":       billing_raw.get("phone", ""),
                "card_number": billing_raw.get("card_number", ""),
                "expiry":      billing_raw.get("expiry", ""),
                "cvv":         billing_raw.get("cvv", ""),
            },
        )


class ProfileLoader:
    def __init__(self, config_path: str):
        self.config_path = config_path

    def load(self) -> List[Profile]:
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
    loader = ProfileLoader(config_path)
    return loader.load()
