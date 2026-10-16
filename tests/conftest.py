from pathlib import Path

def pytest_configure(config):
    Path("data").mkdir(exist_ok=True)
