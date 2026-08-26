from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


spec_location = Path(SPECPATH).resolve()
spec_directory = spec_location if spec_location.is_dir() else spec_location.parent
project_root = spec_directory.parent
demo_datas, demo_binaries, demo_hiddenimports = collect_all("demoparser2")
polars_datas, polars_binaries, polars_hiddenimports = collect_all("polars")

datas = list(demo_datas) + list(polars_datas)
for relative, destination in (
    ("chapter07_cs2_coach/web", "chapter07_cs2_coach/web"),
    ("chapter07_cs2_coach/knowledge", "chapter07_cs2_coach/knowledge"),
    ("chapter07_cs2_coach/evaluation", "chapter07_cs2_coach/evaluation"),
):
    datas.append((str(project_root / relative), destination))

hiddenimports = sorted(
    set(
        demo_hiddenimports
        + polars_hiddenimports
        + collect_submodules("langgraph")
        + ["email_validator", "pydantic_core"]
    )
)

analysis = Analysis(
    [str(project_root / "chapter07_cs2_coach/local_server.py")],
    pathex=[str(project_root)],
    binaries=demo_binaries + polars_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["alembic", "boto3", "botocore", "celery", "pgvector", "psycopg", "redis"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="RoundMind-Local-Parser",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)
bundle = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="RoundMind-Local-Parser",
)
