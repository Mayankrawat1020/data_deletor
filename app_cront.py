from flask import Flask, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
from datetime import datetime
import re 
# Database configurations
DATABASES = {
    "Test_Globe1": {
        "host": "localhost",
        "port": 5432,
        "database": "Test_Globe1",
        "user": "postgres",
        "password": "mayank"
    },
    "Test_Delete": {
        "host": "localhost",
        "port": 5432,
        "database": "Test_Delete",
        "user": "postgres",
        "password": "mayank"
    }
}

# Utility function to get a database connection
def get_db_connection(db_name):
    config = DATABASES[db_name]
    return psycopg2.connect(
        host=config["host"],
        port=config["port"],
        database=config["database"],
        user=config["user"],
        password=config["password"]
    )
def is_valid_date_format(value):
    """
    Checks if the given value is in a valid date format: YYYY-MM-DD (Case 1) or DD-MM-YYYY (Case 2).
    """
    if not value or not isinstance(value, str):  # Ensure value is a string
        return False, None
    
    value = value.strip()  # Remove spaces before checking format
    
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):  # YYYY-MM-DD
        print("case 1")
        return True, 1
    elif re.match(r"^\d{2}-\d{2}-\d{4}$", value):  # DD-MM-YYYY
        print("case 2")
        return True, 2
    else:
        print("False case")
        return False, None


def delete_expired_records():
    try:
        # Connect to global1 database for delete_data and delete_data_log
        global_conn = get_db_connection("Test_Globe1")
        global_cursor = global_conn.cursor()
        
        today_date = datetime.today().date()
        print(f"checking todays' date {today_date} ")
        # Fetch tables that need deletion today
        global_cursor.execute("""
            SELECT database_name, table_name, key_column, record_keep_days, frequency
            FROM delete_data
            WHERE next_run_date = %s
            ORDER BY table_name;
        """, (today_date,))
        
        tables_to_delete = global_cursor.fetchall()
        
        print(f"tables in todays's run date are{tables_to_delete}")
        
        
        for table in tables_to_delete:
            
            print(f"tables in todays's run date inside loop  are{table}")
            database_name, table_name, key_column, record_keep_days, frequency = table
            
            # Connect to the respective database for fetching column details and deletion
            db_conn = get_db_connection(database_name)
            db_cursor = db_conn.cursor()
            
            # Get column data type
            db_cursor.execute("""
                SELECT data_type, table_schema
                FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s;
            """, (table_name, key_column))
            
            column_info = db_cursor.fetchone()
            if not column_info:
                print(f"Column {key_column} not found in {table_name}.")
                db_cursor.close()
                db_conn.close()
                continue
            
            column_type, schema_name = column_info
            column_type = column_type.lower()
            
            # Determine deletion query based on column type
            if  "date" in column_type:
                print("inside date type")
                delete_query = sql.SQL("""
                    DELETE FROM {schema}.{table}
                    WHERE {key_column} <= (SELECT MAX({key_column}) - INTERVAL %s FROM {schema}.{table})
                """).format(
                    schema=sql.Identifier(schema_name),
                    table=sql.Identifier(table_name),
                    key_column=sql.Identifier(key_column)
                )
                db_cursor.execute(delete_query, (f"{record_keep_days} days",))

            elif "timestamp" in column_type :
                delete_query = sql.SQL("""
                    DELETE FROM {schema}.{table}
                    WHERE {key_column} < (SELECT MAX({key_column}) - INTERVAL %s FROM {schema}.{table})
                """).format(
                    schema=sql.Identifier(schema_name),
                    table=sql.Identifier(table_name),
                    key_column=sql.Identifier(key_column)
                )
                db_cursor.execute(delete_query, (f"{record_keep_days} days",))
            
            elif "char" or "varchar" or "text" in column_type:  # Handles VARCHAR, TEXT, CHAR
                # Check if values in this column have valid date formats
                db_cursor.execute(sql.SQL("""
                    SELECT DISTINCT {key_column} FROM {schema}.{table} LIMIT 5;
                """).format(
                    schema=sql.Identifier(schema_name),
                    table=sql.Identifier(table_name),
                    key_column=sql.Identifier(key_column)
                ))

                sample_values = db_cursor.fetchall()
                valid_format = None
                is_valid, case_type = False, None 

                for row in sample_values:
                    is_valid, case_type = is_valid_date_format(row[0])
                    if is_valid:
                        valid_format = case_type
                        break
                
                print(f"values for is_valid: {is_valid} ")
                print(f"values for case_type: {case_type} ")

                if valid_format is None:
                    print(f"Error: Column '{key_column}' contains invalid date formats for deletion.")
                    return  


                if valid_format == 1:  # YYYY-MM-DD
                    delete_query = sql.SQL("""
                        DELETE FROM {table}
                        WHERE TO_DATE({key_column}, 'YYYY-MM-DD') <= (
                        SELECT MAX(TO_DATE({key_column}, 'YYYY-MM-DD')) FROM {table}
                        ) - INTERVAL %s
                    """).format(
                        table=sql.Identifier(table_name),
                        key_column=sql.Identifier(key_column)
                    )
                elif valid_format == 2:  # DD-MM-YYYY
                    print("inside format 2 ")
                    delete_query = sql.SQL("""
                        DELETE FROM {table}
                        WHERE TO_DATE({key_column}, 'DD-MM-YYYY') <= (
                        SELECT MAX(TO_DATE({key_column}, 'DD-MM-YYYY')) FROM {table}
                        ) - INTERVAL %s
                    """).format(
                        table=sql.Identifier(table_name),
                        key_column=sql.Identifier(key_column)
                    )

                    db_cursor.execute(delete_query, (f"{record_keep_days} days",))

                else:
                    return jsonify({"error": "Unsupported key column type"}), 400

            
            else:
                print(f"Unsupported key column type in {table_name}.")
                
            
            deleted_count = db_cursor.rowcount
            db_conn.commit()
            
            # Log deletion into delete_data_log in global1 database
            if deleted_count >= 0:
                global_cursor.execute("""
                    INSERT INTO delete_data_log (server_name, database_name, table_name, record_keep_days, records_deleted, execution_date,user_executing,status)
                    VALUES (%s, %s, %s, %s, %s, NOW(),%s,%s);
                """, ("localhost", database_name, table_name, record_keep_days, deleted_count,'cront',f'sucessfully deleted {deleted_count} records'))
                global_conn.commit()
            
            # Update next_run_date in delete_data table in global1 database
            global_cursor.execute("""
                UPDATE delete_data
                SET next_run_date = CURRENT_DATE + INTERVAL '1 day' * %s
                WHERE table_name = %s;
            """, (frequency, table_name))
            global_conn.commit()
            
            print(f"Deleted {deleted_count} records from {table_name} in {database_name}.")
            
        
        global_cursor.close()
        global_conn.close()
        
    except Exception as e:
        error_message = str(e)
        print(f"Error: {error_message}")

        try:
            if global_conn is None:
                global_conn = get_db_connection("Test_Globe1")
                global_cursor = global_conn.cursor()
            #global_conn = get_db_connection("Test_Globe1")
            #global_cursor = global_conn.cursor()
            error_message = error_message[:60]  

            print("inside exception")

            # Insert error log into delete_data_log
            global_cursor.execute("""
                INSERT INTO delete_data_log (server_name, database_name, table_name, record_keep_days, records_deleted, execution_date, user_executing, status)
                VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s);
            """,  ("localhost", database_name, table_name, record_keep_days, 0, 'cront', f'{error_message} reschdeuled for {frequency} days  later ')) # Table & DB unknown in failure case
            global_conn.commit()


            global_cursor.execute("""
                UPDATE delete_data
                SET next_run_date = CURRENT_DATE + INTERVAL '1 day' * %s
                WHERE table_name = %s;
            """, (frequency, table_name))
            global_conn.commit()
            global_cursor.close()
            global_conn.close()
            delete_expired_records()
        except Exception as log_error:
            print(f"Failed to log error: {log_error}")

   

if __name__ == '__main__':
    delete_expired_records()
