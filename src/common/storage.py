
import json
import os 


def load_state(path):

  if not os.path.exists(path):
    return{"current_term": 0, "voted_for":None}

  with open(path) as f: 
    return json.load(f)


def save_state(path, current_term, voted_for):
   folder = os.path.dirname(path)
   if folder:
     os.makedirs(folder, exist_ok=True)
   tmp = path + ".tmp"
   with open(tmp, "w") as f:
        json.dump({"current_term": current_term, "voted_for": voted_for}, f)
   os.replace(tmp, path)
