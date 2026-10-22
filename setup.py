from setuptools import setup

setup(
    name="pyorganize",
    version="2.0.0",
    description="Smart CLI & GUI File Organizer with AI Context Sorting (Gemini, ChatGPT, DeepSeek, Claude)",
    py_modules=["pyorganize", "ai_organizer", "gui"],
    install_requires=["flet>=0.25.0"],
    entry_points={
        "console_scripts": [
            "pyorganize=pyorganize:main",
            "pyorganize-gui=gui:run_gui",
        ],
    },
    python_requires=">=3.9",
)
