"""dirtyloader -- an Elekloader-style mod loader for Dirtywave M8 firmware.

Public API:
    M8Firmware, Patch, M8FWError  -- the "M8FW" container (m8fw)
    Mod, Site, make_target        -- the .m8mod format, format 2 (m8mod; docs/FORMAT.md)
    link, diff_payloads           -- combine mods onto stock firmware (linker)
    registry                      -- known stock-firmware identification
"""
from dirtyloader.m8fw import M8Firmware, Patch, M8FWError, crc32
from dirtyloader.m8mod import Mod, Site, M8MOD_FORMAT, make_target
from dirtyloader.linker import link, diff_payloads, ConflictError
from dirtyloader import registry

__all__ = [
    "M8Firmware", "Patch", "M8FWError", "crc32",
    "Mod", "Site", "M8MOD_FORMAT", "make_target",
    "link", "diff_payloads", "ConflictError",
    "registry",
]
__version__ = "0.2.0"
