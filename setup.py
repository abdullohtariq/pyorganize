from setuptools import setup, find_packages

setup(
    name="pyorganize",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[],
    entry_points={
        "console_scripts": [
            "pyorganize=pyorganize.pyorganize:main",
        ],
    },
)