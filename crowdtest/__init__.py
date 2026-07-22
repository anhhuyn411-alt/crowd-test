"""crowd-test: hire a crowd of AI virtual users to test your web app."""

__version__ = "0.1.0"

from crowdtest.persona import Persona, load_persona, load_builtin_personas
from crowdtest.results import Finding, PersonaResult, CrewResult

__all__ = [
    "Persona",
    "load_persona",
    "load_builtin_personas",
    "Finding",
    "PersonaResult",
    "CrewResult",
]
