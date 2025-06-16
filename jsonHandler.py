import json
import os

class JsonHandler:
    def __init__(self, filename: str):
        self.filename = filename
        self.map = {}
        self.load()

    def load(self):
        if not os.path.exists(self.filename):
            print(f"[JsonHandler] File '{self.filename}' not found. Starting fresh.")
            self.map = {}
            return

        try:
            with open(self.filename, "r") as file:
                data = json.load(file)
                # Ensure keys are integers again (because JSON saves them as strings)
                self.map = {int(k): v for k, v in data.items()}
            print(f"[JsonHandler] Successfully loaded data from {self.filename}")
        except Exception as e:
            print(f"[JsonHandler] Failed to load JSON: {e}")
            self.map = {}

    def save(self):
        # Ensure message IDs are saved as strings
        serializable_map = {str(k): v for k, v in self.map.items()}
        with open(self.filename, "w") as file:
            json.dump(serializable_map, file, indent=4)
        print(f"[JsonHandler] Saved to {self.filename}")
