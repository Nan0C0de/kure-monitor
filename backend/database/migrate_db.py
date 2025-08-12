import sqlite3
import sys

def migrate_database(db_path="kure.db"):
    """Add manifest column to existing database if it doesn't exist"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if manifest column exists
        cursor.execute("PRAGMA table_info(pod_failures)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'manifest' not in columns:
            print("Adding manifest column to database...")
            cursor.execute("ALTER TABLE pod_failures ADD COLUMN manifest TEXT DEFAULT ''")
            conn.commit()
            print("Database migration completed successfully!")
        else:
            print("Database is already up to date.")
            
    except Exception as e:
        print(f"Migration failed: {e}")
        return False
    finally:
        conn.close()
        
    return True

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "kure.db"
    migrate_database(db_path)