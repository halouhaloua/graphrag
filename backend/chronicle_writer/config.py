from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ChronicleConfig:
    default_chronicle_type: str = "town"
    max_outline_depth: int = 4
    max_review_iterations: int = 3
    quality_threshold: float = 0.8
    default_temperature: float = 0.3
    verify_confidence_threshold: float = 0.6
    skills_dir: str = ""
    template_dir: str = ""
    default_model_temperature: float = 0.3


_config: Optional[ChronicleConfig] = None


def get_chronicle_config() -> ChronicleConfig:
    global _config
    if _config is None:
        base = Path(__file__).parent
        _config = ChronicleConfig(
            skills_dir=str(base / "skills"),
            template_dir=str(base / "templates"),
        )
    return _config
