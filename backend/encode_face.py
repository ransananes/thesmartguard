"""
Standalone face encoding script.
Run in a subprocess to isolate crashes from the main Flask process.
Usage: python encode_face.py <image_path>
Outputs: JSON with encoding or error
"""
import sys
import json
import face_recognition
import numpy as np

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No image path provided"}))
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    try:
        img = face_recognition.load_image_file(image_path)
        encodings = face_recognition.face_encodings(img)
        
        if encodings:
            # Convert numpy array to list for JSON serialization
            encoding_list = encodings[0].tolist()
            print(json.dumps({"success": True, "encoding": encoding_list}))
        else:
            print(json.dumps({"success": False, "error": "No face found in image"}))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
