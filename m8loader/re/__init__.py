"""Reverse-engineering tooling for dirtyloader.

These modules support *authoring* mods and the Core (boot-structure parsing,
code-cave surveying, Ghidra ingestion). They may use optional third-party tools
(capstone, Ghidra); the core patcher package (m8loader.m8fw/m8mod/linker) stays
dependency-free and does not import this subpackage.
"""
