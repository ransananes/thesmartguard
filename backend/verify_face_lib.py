import sys
try:
    import face_recognition
    import dlib
    print("Face recognition and dlib imported successfully!")
    print(f"dlib version: {dlib.__version__}")
    print(f"face_recognition version: {face_recognition.__version__}")
except ImportError as e:
    print(f"Failed to import: {e}")
    sys.exit(1)
except Exception as e:
    print(f"An error occurred: {e}")
    sys.exit(1)
