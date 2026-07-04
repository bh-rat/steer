"""
Project scaffolding helpers for CLI tools.

Creates directory structures and writes template files with skip-if-exists
behavior. Used by init commands to set up new projects.

Usage:
    from steer.scaffold import scaffold_project, FileSpec

    result = scaffold_project("./my-project", files=[
        FileSpec("config/settings.yaml", content, "configure data sources"),
        FileSpec("config/rules.txt", rules_content, "define rules"),
    ], dirs=["data", "output"])

    print(result.created)   # ["config/settings.yaml", "config/rules.txt"]
    print(result.skipped)   # []
"""

import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class FileSpec:
    """Specification for a file to create during scaffolding."""
    path: str               # Relative path from target_dir
    content: str            # File content (already formatted)
    description: str = ""   # Human-readable description for display


@dataclass
class ScaffoldResult:
    """Result of a scaffold_project() call."""
    created: List[str]      # Files that were created
    skipped: List[str]      # Files that already existed (not overwritten)


def scaffold_project(target_dir: str, files: List[FileSpec],
                     dirs: Optional[List[str]] = None) -> ScaffoldResult:
    """Create a project directory structure from file specs.

    Creates directories and writes files. Skips files that already exist
    (never overwrites). Creates parent directories as needed.

    Args:
        target_dir: Root directory for the project.
        files: List of FileSpec describing files to create.
        dirs: Optional list of directory paths to create (even if empty).

    Returns:
        ScaffoldResult with lists of created and skipped files.
    """
    created = []
    skipped = []

    # Create explicit directories (even if empty)
    if dirs:
        for d in dirs:
            os.makedirs(os.path.join(target_dir, d), exist_ok=True)

    # Write files
    for spec in files:
        full_path = os.path.join(target_dir, spec.path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        if os.path.exists(full_path):
            skipped.append(spec.path)
        else:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(spec.content)
            created.append(spec.path)

    return ScaffoldResult(created=created, skipped=skipped)
