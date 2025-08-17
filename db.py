import mysql.connector
import logging

logging.basicConfig(level=logging.DEBUG)

def get_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",  # Update with your MySQL root password if set
            database="nasheeman_db"
        )
        if not conn.is_connected():
            logging.error("Failed to establish database connection")
            raise mysql.connector.Error("Connection not established")
        logging.info("Successfully connected to nasheeman_db")
        return conn
    except mysql.connector.Error as e:
        logging.error(f"Database connection failed: {str(e)}")
        raise  # Re-raise to be caught by the calling function
