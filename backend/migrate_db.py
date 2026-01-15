import sqlite3
import os
from werkzeug.security import generate_password_hash

# Path to db
db_path = os.path.join('app', 'smartguard.db')

print(f"Connecting to database at {db_path}...")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check columns
    # Check columns for user table
    cursor.execute("PRAGMA table_info(user)")
    columns = [info[1] for info in cursor.fetchall()]
    print(f"Current user columns: {columns}")
    
    if 'password_hash' not in columns:
        print("Adding password_hash column...")
        cursor.execute("ALTER TABLE user ADD COLUMN password_hash VARCHAR(128)")
        conn.commit()
        print("Column added.")
    else:
        print("password_hash column already exists.")

    # Check columns for camera table
    cursor.execute("PRAGMA table_info(camera)")
    camera_columns = [info[1] for info in cursor.fetchall()]
    print(f"Current camera columns: {camera_columns}")

    if 'ip_address' not in camera_columns:
        print("Adding ip_address column...")
        cursor.execute("ALTER TABLE camera ADD COLUMN ip_address VARCHAR(50)")
        conn.commit()
        print("ip_address column added.")
    
    if 'port' not in camera_columns:
        print("Adding port column...")
        cursor.execute("ALTER TABLE camera ADD COLUMN port INTEGER")
        conn.commit()
        print("port column added.")

    # Check for detection table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='detection'")
    if not cursor.fetchone():
        print("Creating detection table...")
        cursor.execute('''
            CREATE TABLE detection (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id INTEGER NOT NULL,
                label VARCHAR(50) NOT NULL,
                confidence FLOAT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (camera_id) REFERENCES camera (id)
            )
        ''')
        conn.commit()
        print("detection table created.")
    else:
        print("detection table already exists.")

    # Update root user
    print("Updating root password...")
    p_hash = generate_password_hash('root')
    cursor.execute("UPDATE user SET password_hash = ? WHERE username = 'root'", (p_hash,))
    conn.commit()
    print("Root password updated.")
    
    conn.close()
    print("Migration complete.")
    
except Exception as e:
    print(f"An error occurred: {e}")
