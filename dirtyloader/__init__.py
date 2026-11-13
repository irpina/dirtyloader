"""dirtyloader -- an Elekloader-style mod patcher for Dirtywave M8 firmware.

Public API:
    M8Firmware, Patch, M8FWError  -- the "M8FW" container (m8fw)
    Mod, ModPatch                 -- the .m8mod mod package format (m8mod)
    link, diff_payloads           -- combine mods onto stock firmware (linker)
    registry                      -- known stock-firmware identification
"""
from dirtyloader.m8fw import M8Firmware, Patch, M8FWError, crc32
from dirtyloader.m8mod import Mod, ModPatch, M8MOD_FORMAT
from dirtyloader.linker import link, diff_payloads, ConflictError
from dirtyloader import registry

__all__ = [
    "M8Firmware", "Patch", "M8FWError", "crc32",
    "Mod", "ModPatch", "M8MOD_FORMAT",
    "link", "diff_payloads", "ConflictError",
    "registry",
]
__version__ = "0.1.0"
