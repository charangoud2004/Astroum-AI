"""Configuration loader for BRAHMO Clinical AI.

Loads config/config.yaml into strongly typed dataclasses and provides
convenient access to all system parameters, paths, and thresholds.
Zero hardcoding permitted in business logic.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union
import yaml


@dataclass(frozen=True)
class PathsConfig:
    """Directory and file paths for system operations."""
    data_dir: str
    corpus_dir: str
    db_path: str
    migrations_dir: str
    outputs_dir: str


@dataclass(frozen=True)
class DatasetsConfig:
    """Input dataset filenames."""
    cdci_file: str
    nlem_file: str
    jan_aushadhi_file: str
    regulatory_events_file: str
    pharmacy_stock_file: str
    severe_interactions_file: str
    seed_prescriptions_file: str
    sample_questions_file: str
    local_protocol_file: str


@dataclass(frozen=True)
class SafetyRailConfig:
    """Module A deterministic safety rail parameters."""
    as_of_date: str
    adult_paracetamol_daily_warn_mg: float
    fuzzy_match_review_threshold: float


@dataclass(frozen=True)
class RetrievalConfig:
    """Module B retrieval parameters."""
    top_k_lexical: int
    top_k_semantic: int
    rrf_k: int
    embedding_model: str


@dataclass(frozen=True)
class LLMConfig:
    """Module B generation and provider parameters."""
    llm_provider: str
    llm_model: str
    temperature: float


@dataclass(frozen=True)
class AppConfig:
    """Root configuration object representing config/config.yaml."""
    paths: PathsConfig
    datasets: DatasetsConfig
    safety_rail: SafetyRailConfig
    retrieval: RetrievalConfig
    llm: LLMConfig
    raw_dict: Dict[str, Any] = field(default_factory=dict, repr=False)
    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent, repr=False)

    def get_data_path(self, filename_key: str) -> Path:
        """Resolve a dataset file path within data_dir."""
        filename = getattr(self.datasets, filename_key, None)
        if not filename:
            raise KeyError(f"Unknown dataset key: {filename_key}")
        data_dir = self.resolve_path(self.paths.data_dir)
        return data_dir / filename

    def resolve_path(self, path_str: str) -> Path:
        """Resolve a relative or absolute path against the project root."""
        p = Path(path_str)
        if p.is_absolute():
            return p
        return (self.project_root / p).resolve()


_CACHED_CONFIG: Optional[AppConfig] = None


def find_project_root() -> Path:
    """Determine the project root directory containing config/config.yaml."""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "config" / "config.yaml").is_file():
            return parent
    # Default to current file's parent's parent
    return Path(__file__).resolve().parent.parent


def load_config(config_path: Optional[Union[str, Path]] = None, reload: bool = False) -> AppConfig:
    """Load and parse config.yaml into an AppConfig instance.

    Args:
        config_path: Optional path to config.yaml. If None, resolves from project root.
        reload: If True, bypass cached instance.

    Returns:
        AppConfig typed dataclass.
    """
    global _CACHED_CONFIG
    if _CACHED_CONFIG is not None and not reload:
        return _CACHED_CONFIG

    project_root = find_project_root()

    if config_path is None:
        target_file = project_root / "config" / "config.yaml"
    else:
        target_file = Path(config_path)
        if not target_file.is_absolute():
            target_file = (project_root / target_file).resolve()

    if not target_file.is_file():
        raise FileNotFoundError(f"Configuration file not found at: {target_file}")

    with open(target_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    paths_data = data.get("paths", {})
    datasets_data = data.get("datasets", {})
    safety_data = data.get("safety_rail", {})
    retrieval_data = data.get("retrieval", {})
    llm_data = data.get("llm", {})

    paths = PathsConfig(
        data_dir=str(paths_data.get("data_dir", "data")),
        corpus_dir=str(paths_data.get("corpus_dir", "corpus")),
        db_path=str(paths_data.get("db_path", "data/brahmo.db")),
        migrations_dir=str(paths_data.get("migrations_dir", "migrations")),
        outputs_dir=str(paths_data.get("outputs_dir", "outputs")),
    )

    datasets = DatasetsConfig(
        cdci_file=str(datasets_data.get("cdci_file", "cdci_drug_subset.csv")),
        nlem_file=str(datasets_data.get("nlem_file", "nlem_extract.csv")),
        jan_aushadhi_file=str(datasets_data.get("jan_aushadhi_file", "jan_aushadhi_extract.csv")),
        regulatory_events_file=str(datasets_data.get("regulatory_events_file", "regulatory_gazette_events.csv")),
        pharmacy_stock_file=str(datasets_data.get("pharmacy_stock_file", "pharmacy_stock.csv")),
        severe_interactions_file=str(datasets_data.get("severe_interactions_file", "severe_interaction_seed.csv")),
        seed_prescriptions_file=str(datasets_data.get("seed_prescriptions_file", "seed_prescriptions_template.csv")),
        sample_questions_file=str(datasets_data.get("sample_questions_file", "sample_questions.md")),
        local_protocol_file=str(datasets_data.get("local_protocol_file", "local_protocol_acute_fever.md")),
    )

    safety_rail = SafetyRailConfig(
        as_of_date=str(safety_data.get("as_of_date", "2026-10-15")),
        adult_paracetamol_daily_warn_mg=float(safety_data.get("adult_paracetamol_daily_warn_mg", 3000.0)),
        fuzzy_match_review_threshold=float(safety_data.get("fuzzy_match_review_threshold", 0.80)),
    )

    retrieval = RetrievalConfig(
        top_k_lexical=int(retrieval_data.get("top_k_lexical", 5)),
        top_k_semantic=int(retrieval_data.get("top_k_semantic", 5)),
        rrf_k=int(retrieval_data.get("rrf_k", 60)),
        embedding_model=str(retrieval_data.get("embedding_model", "all-MiniLM-L6-v2")),
    )

    llm = LLMConfig(
        llm_provider=str(llm_data.get("llm_provider", "groq")),
        llm_model=str(llm_data.get("llm_model", "llama-3.3-70b-versatile")),
        temperature=float(llm_data.get("temperature", 0.0)),
    )

    app_config = AppConfig(
        paths=paths,
        datasets=datasets,
        safety_rail=safety_rail,
        retrieval=retrieval,
        llm=llm,
        raw_dict=data,
        project_root=project_root,
    )

    _CACHED_CONFIG = app_config
    return app_config


def get_config() -> AppConfig:
    """Retrieve global cached configuration or load default."""
    global _CACHED_CONFIG
    if _CACHED_CONFIG is None:
        return load_config()
    return _CACHED_CONFIG
