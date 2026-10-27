from __future__ import annotations

import importlib.metadata


def main() -> None:
    packages = ("numpy", "pandas", "scipy", "lightgbm", "lxml", "pypdf", "PyMuPDF", "Pillow", "python-docx")
    for package in packages:
        print(f"{package}=={importlib.metadata.version(package)}")


if __name__ == "__main__":
    main()
