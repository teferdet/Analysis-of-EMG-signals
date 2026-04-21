import csv

# Base storage data
file: dict = {
    "filename": "EMG-data.csv",
    "path": ".data/EMG-data.csv",
}

# Update name and path after change direction
def update(path):
    print(path.split("/")[-1])
    file["filename"] = path.split("/")[-1]
    file["path"] = path

def read(path):
    ...