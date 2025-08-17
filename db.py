import mysql.connector
import logging

logging.basicConfig(level=logging.DEBUG)

def get_connection():
    try:
        conn = mysql.connector.connect(
            host="db4free.net",
            user="nasheeman_user",        # <-- your db4free username
            password="Nasheeman@123",     # <-- your db4free password
            database="nasheeman_db",      # <-- your db4free db name
            port=3306
        )
        if not conn.is_connected():
            logging.error("Failed to establish database connection")
            raise mysql.connector.Error("Connection not established")
        logging.info("✅ Successfully connected to db4free (nasheeman_db)")
        return conn
    except mysql.connector.Error as e:
        logging.error(f"❌ Database connection failed: {str(e)}")
        raise
