from __future__ import annotations

from .acebench import ACEBench
from .bfcl import BFCL
from .mind2web import Mind2Web
from .officebench import OfficeBench
from .operating_system import OperatingSystem
from .sheetcopilot import SheetCopilot
from .tau2bench import Tau2Bench
from .webshop import WebShop

ENVIRONMENTS = {
    environment.name: environment
    for environment in (WebShop, Mind2Web, SheetCopilot, OperatingSystem, OfficeBench, ACEBench, BFCL, Tau2Bench)
}


def load_environment(config):
    if config.environment not in ENVIRONMENTS:
        raise ValueError(f"unknown environment {config.environment}; one of {sorted(ENVIRONMENTS)}")
    return ENVIRONMENTS[config.environment]()
