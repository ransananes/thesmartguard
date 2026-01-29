import sys
import os

# Add the backend directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.append(backend_dir)

import numpy as np
from app import create_app
from app.models import KnownFace

app = create_app()

with app.app_context():
    faces = KnownFace.query.all()
    print(f"Found {len(faces)} known faces in database:")
    
    for f in faces:
        enc = f.encoding
        if enc is not None:
            enc_arr = np.array(enc)
            encoding_sum = np.sum(np.abs(enc_arr))
            is_valid = encoding_sum > 1.0  # A real encoding will have sum >> 0
            print(f"  - ID {f.id}: '{f.name}' | encoding_sum={encoding_sum:.4f} | valid={is_valid}")
        else:
            print(f"  - ID {f.id}: '{f.name}' | encoding=None | valid=False")
