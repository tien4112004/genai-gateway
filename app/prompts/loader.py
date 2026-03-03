from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from string import Template
from typing import Any, Dict, Optional

import yaml

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / "registry.yaml"

"""
Prompt loading and rendering with variable substitution.
"""


class _DefaultDict(dict):
    """Dict that returns an empty string for missing keys during template substitution."""

    def __missing__(self, key: str) -> str:
        return ""


@dataclass
class PromptSpec:
    key: str
    path: Path
    format: str = "st"
    defaults_path: Optional[Path] = None


class PromptStore:
    """
    Load and render prompts from a registry.
    """

    def __init__(self, base_dir: Path = ROOT):
        self.base = base_dir

    @lru_cache(maxsize=64)
    def _load_registry(self) -> Dict[str, Any]:
        """Load the prompt registry from a YAML file."""
        with open(REGISTRY, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _spec(self, key: str) -> PromptSpec:
        """
        Get the PromptSpec for a given key.
        Raises KeyError if the key is not found.
        Args:
            key: The prompt key to look up.
        Returns:
            PromptSpec: The specification for the prompt.
        Raises:
            KeyError: If the prompt key is not found in the registry.
        """
        reg = self._load_registry().get("prompts", {})

        if key not in reg:
            raise KeyError(f"Prompt key not found: {key}")

        entry = reg[key]
        path = self.base / entry["path"]
        fmt = entry.get("format", "st")
        defaults = entry.get("defaults")
        defaults_path = self.base / defaults if defaults else None

        return PromptSpec(
            key=key, path=path, format=fmt, defaults_path=defaults_path
        )

    @lru_cache(maxsize=128)
    def _load_text(self, path: Path) -> str:
        """
        Load the text content of a prompt file.
        Args:
            path: The path to the prompt file.
        Returns:
            str: The content of the prompt file.
        """
        return path.read_text(encoding="utf-8")

    def _load_defaults(self, spec: PromptSpec) -> Dict[str, Any]:
        """
        Load default variables from a YAML file if specified.
        Args:
            spec: The PromptSpec containing the defaults_path.
        Returns:
            Dict[str, Any]: The default variables.
        """
        if not spec.defaults_path or not spec.defaults_path.exists():
            return {}

        return (
            yaml.safe_load(spec.defaults_path.read_text(encoding="utf-8"))
            or {}
        )

    def render(self, key: str, vars: Dict[str, Any] | None) -> str:
        """
        Render a prompt by substituting variables into the template.
        Args:
            key: The prompt key to render.
            vars: A dictionary of variables to substitute into the prompt.
        Returns:
            str: The rendered prompt text.
        """
        spec = self._spec(key)
        text = self._load_text(spec.path)

        if vars is None:
            vars = {}
        merged = {**self._load_defaults(spec), **vars}

        # add partials (e.g., ${safety_rules}) as simple include
        safety_path = self.base / "common/safety.st"
        if safety_path.exists():
            merged.setdefault(
                "safety_rules", self._load_text(safety_path).strip()
            )

        rendered_text = Template(text).substitute(_DefaultDict(merged))

        return rendered_text
