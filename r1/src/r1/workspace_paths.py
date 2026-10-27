from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
WORKSPACE = PROJECT if (PROJECT / "src" / "ask").is_dir() else PROJECT.parents[1]
ORIGINAL_DATA = PROJECT / "data" / "original_study"
if not ORIGINAL_DATA.is_dir():
    ORIGINAL_DATA = WORKSPACE
FORMAL_DATA = PROJECT / "data" / "formal_api_records"
if not FORMAL_DATA.is_dir():
    FORMAL_DATA = PROJECT / "data" / "api_r1" / "paired"
