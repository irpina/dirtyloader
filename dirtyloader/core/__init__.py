"""
The dirtyloader Core.

The Core is a small piece of firmware-side infrastructure, injected as a special
mod (`id: "core"`), that lets multiple mods hook the same firmware code without
clobbering each other -- the equivalent of Elekloader's core mod + event bus.

Other mods declare `requires: ["core"]` and register handlers against named
events; at each hooked site the Core's dispatcher walks its handler table and
calls every registered handler in turn.

This package holds the loader-side half: the ABI constants and layout shared by
the Core builder and by mods. The firmware-side half (the Thumb dispatcher and
trampolines) is assembled into a reserved code cave -- see docs/CORE.md.

Status: design + provisional ABI. Hook addresses are bound after the Ghidra
function map lands and must be validated on hardware before real use.
"""
from dirtyloader.core import abi

__all__ = ["abi"]
