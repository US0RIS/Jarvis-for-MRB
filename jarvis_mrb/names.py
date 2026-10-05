"""Canonical user-facing names for the HORUS architecture.

Internal package/module names remain stable for compatibility.  These names are the
public vocabulary exposed by status, UI, logs, and future subsystem facades.
"""

SYSTEM_NAME = "HORUS"
SYSTEM_DISPLAY_NAME = "Horus"
LEGACY_DESCRIPTION = "a real-world Jarvis"

KANT = "Kant"
CARCOSA = "Carcosa"
ARIADNE = "Ariadne"
CASSANDRA = "Cassandra"
MNEMOSYNE = "Mnemosyne"
CERBERUS = "Cerberus"
MERCURY = "Mercury"
SISYPHUS = "Sisyphus"

SUBSYSTEMS = {
    "deep_reasoning": KANT,
    "historical_world": CARCOSA,
    "investigation": ARIADNE,
    "predictive_warnings": CASSANDRA,
    "memory": MNEMOSYNE,
    "security": CERBERUS,
    "communications": MERCURY,
    "background_repair": SISYPHUS,
}

def subsystem_name(capability: str) -> str:
    return SUBSYSTEMS.get(str(capability).strip().lower(), str(capability))
