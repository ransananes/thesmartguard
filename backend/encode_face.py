import sys
import json
import face_recognition
import numpy as np
import logging  

logger = logging.getLogger(__name__)

def main():
    if len(sys.argv) < 2:
        logger.info(json.dumps({"error": "No image path provided"}))
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    try:
        img = face_recognition.load_image_file(image_path)
        encodings = face_recognition.face_encodings(img)
        
        if encodings:
            encoding_list = encodings[0].tolist()
            logger.info(json.dumps({"success": True, "encoding": encoding_list}))
        else:
            logger.info(json.dumps({"success": False, "error": "No face found in image"}))
    except Exception as e:
        logger.error(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
