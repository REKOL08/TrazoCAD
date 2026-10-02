from pathlib import Path

from setuptools import find_packages, setup

long_description = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")

setup(
    name="planos2dwg",
    version="1.0.0",
    description="Convierte planos PDF escaneados a archivos DXF/DWG editables.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(include=["src", "src.*"]),
    install_requires=[
        "pymupdf>=1.24,<2.0",
        "opencv-python>=4.9,<5.0",
        "numpy>=1.26,<3.0",
        "ezdxf>=1.3,<2.0",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "planos2dwg=main:main",
        ],
    },
)
