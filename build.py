import PyInstaller.__main__
import os

def build_project():
    print("Start...")
    separator = os.pathsep

    args = [
        'main.py',
        '--name=Analysis of EMG signals',
        '--onefile',
        '--clean',
        f'--add-data=data{separator}data',
        f'--add-data=src{separator}src',
        '--windowed',
        '--icon=data/program.ico',
    ]

    try:
        PyInstaller.__main__.run(args)
        print("\nSuccess ended!")
    except Exception as e:
        print(f"\nSomethings wrong: {e}")

if __name__ == "__main__":
    build_project()
    input()
