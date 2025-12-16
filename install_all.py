# install_all.py
import subprocess
import sys

packages = [
    ("setuptools", ""),
    ("wheel", ""),
    ("pydantic-core", "2.41.5"),
    ("pydantic", "2.12.5"),
    ("spacy", "3.7.4"),
    ("wikipedia", "1.4.0"),
    ("python-telegram-bot", "20.7"),
    ("python-dotenv", "1.0.0"),
    ("requests", "2.31.0"),
    ("Pillow", "10.2.0"),
    ("clarifai", "2.6.2"),
]

print("=== Установка всех зависимостей ===\n")

for package, version in packages:
    if version:
        package_spec = f"{package}=={version}"
    else:
        package_spec = package
    
    print(f"Устанавливаю: {package_spec}")
    
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", package_spec],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f" {package} установлен")
    else:
        print(f" Ошибка: {result.stderr[:100]}")

print("\n=== Установка модели spaCy ===")
subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])