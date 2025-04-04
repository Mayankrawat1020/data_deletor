import psycopg2
from datetime import datetime

DATABASES = {
    'Test_Globe1': 'postgresql://postgres:mayank@localhost:5432/Test_Globe1'
}

# Utility function to get a database connection
def get_db_connection(db_name):
    if db_name not in DATABASES:
        raise ValueError(f"Database configuration for {db_name} not found.")
    dsn = DATABASES[db_name]  # Get the connection URI
    return psycopg2.connect(dsn)

# Function to insert data into APPLICATION_TABLE
def insert_application_data(database_name, user_name, application_name, table_name, action, status, error_code=None):
    success_names = ['success', 'Success', 'SUCCESS']
    status=status.lower()
    
    # Get current date and time
    current_time = datetime.now()
    access_day = current_time.date()  # YYYY-MM-DD
    access_time = current_time.strftime("%H:%M")  # HH:MM format

    # Ensure ERROR_CODE is strictly required when status is NOT "success"
    if status not in success_names and error_code is None:
        raise ValueError("ERROR_CODE is required when STATUS is not 'success'.")

    # Prepare SQL Query
    if status in success_names:
        query = """
            INSERT INTO APPLICATION_TABLE 
            (DATABASE_NAME, USER_NAME, APPLICATION_NAME, TABLE_NAME, ACTION, ACCESS_DAY, ACCESS_TIME, STATUS, ERROR_CODE) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL);
        """
        values = (database_name, user_name, application_name, table_name, action, access_day, access_time, status)
    else:
        query = """
            INSERT INTO APPLICATION_TABLE 
            (DATABASE_NAME, USER_NAME, APPLICATION_NAME, TABLE_NAME, ACTION, ACCESS_DAY, ACCESS_TIME, STATUS, ERROR_CODE) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        values = (database_name, user_name, application_name, table_name, action, access_day, access_time, status, error_code)

    try:
        conn = get_db_connection('Test_Globe1')
        cursor = conn.cursor()

        # Execute query
        cursor.execute(query, values)
        conn.commit()
        print("Data inserted successfully!")

    except Exception as e:
        print("Error inserting data:", e)
    finally:
        cursor.close()
        conn.close()

