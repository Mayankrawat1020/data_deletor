from flask import Flask, request, jsonify, render_template
import psycopg2
import re
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
from datetime import datetime

app = Flask(__name__)

# Database configurations
DATABASES = {
    'Test_Delete': 'postgresql://postgres:mayank@localhost:5432/Test_Delete',
    'Test_Globe1': 'postgresql://postgres:mayank@localhost:5432/Test_Globe1'
}

# Utility function to get a database connection
def get_db_connection(db_name):

    if db_name not in DATABASES:
        raise ValueError(f"Database configuration for {db_name} not found.")
    dsn = DATABASES[db_name]  # Get the connection URI
    return psycopg2.connect(dsn)  # Use the connection URI directly

@app.route('/')
def home():
    return render_template('indexq.html')  # Your main page



@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.json
    action = data.get('action')

    sql_command = None
    if action == "ANALYZE":
        sql_command = "ANALYZE;"
    elif action == "VACUUM FULL ANALYZE":
        sql_command = "vacuum (full, analyze, INDEX_CLEANUP);"
    elif action == "VACUUM ANALYZE INDEX_CLEANUP":
        sql_command = "VACUUM (ANALYZE, INDEX_CLEANUP);"  

    if sql_command:
        try:
            conn = get_db_connection('Test_Delete')
            conn.autocommit = True  # Enable autocommit mode for VACUUM
            cur = conn.cursor()
            
            print(f"Executing: {sql_command}")
            cur.execute(sql_command)
            print("Execution done")

            cur.close()
            conn.close()
            return jsonify({"message": f"Executed: {sql_command}"})
        except Exception as e:
            print(f"Error executing {sql_command}: {e}")
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Invalid action"}), 400

    

# Route to fetch table names
@app.route('/get-tables', methods=['GET'])
def get_tables():
    database = request.args.get('database')
    if not database:
        return jsonify({"error": "Database is required"}), 400

    try:
        conn = get_db_connection(database)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
        tables = [row['table_name'] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return jsonify(tables)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to fetch column names
@app.route('/get-columns', methods=['GET'])
def get_columns():
    database = request.args.get('database')
    table = request.args.get('table')

    if not database or not table:
        return jsonify({"error": "Database and table are required"}), 400

    try:
        conn = get_db_connection(database)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND trim(table_name) = %s;", (table,))
        columns = [row['column_name'] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return jsonify(columns)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def is_valid_date_format1(value):
    """
    Checks if the given value is in a valid date format: YYYY-MM-DD or DD-MM-YYYY.
    """
    if not value or not isinstance(value, str):  # Ensure value is a string
        return False
    date_patterns = [
        r"^\d{4}-\d{2}-\d{2}$",  # YYYY-MM-DD
        r"^\d{2}-\d{2}-\d{4}$"   # DD-MM-YYYY
    ]
    return any(re.match(pattern, value) for pattern in date_patterns)

# Route to fetch table details (size, record count, min/max date)

@app.route('/get-table-details', methods=['GET'])
def get_table_details():
    database = request.args.get('database')
    table = request.args.get('table')
    key_column = request.args.get('key-column')

    if not (database and table and key_column):
        return jsonify({"error": "Missing required parameters"}), 400

    try:
        conn = get_db_connection(database)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Step 1: Check column data type
        cursor.execute("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s;
        """, (table, key_column))

        column_info = cursor.fetchone()
        if not column_info:
            return jsonify({"error": f"Column '{key_column}' does not exist in table '{table}'"}), 400

        column_type = column_info["data_type"].lower()

        # Allowed data types for min/max date calculation
        allowed_types = {"date", "timestamp", "timestamp without time zone", "timestamp with time zone"}

        is_valid_date_column = True  # Default to true

        if column_type not in allowed_types and column_type not in {"character varying", "varchar", "text"}:
            is_valid_date_column = False  # Column is not a date-like type

        # If column is VARCHAR or TEXT, check if it contains date values
        if column_type in {"character varying", "varchar", "text"}:
            cursor.execute(f'SELECT "{key_column}" FROM "{table}" WHERE "{key_column}" IS NOT NULL LIMIT 10;')
            sample_values = cursor.fetchall()

            # Extract actual values from the result set
            values = [row[key_column] for row in sample_values if row.get(key_column)]

            # If no valid date values are found in the VARCHAR column, mark as invalid
            if not values or not all(is_valid_date_format1(str(value)) for value in values):
                is_valid_date_column = False

        # Default min/max date values if column is not valid for date operations
        min_date = "Key column is not date"
        max_date = "Key column is not date"

        # Fetch min/max only if the column is valid
        if is_valid_date_column:
            query = f"""
                SELECT
                    COUNT(*) AS record_count,
                    MIN("{key_column}") AS min_val,
                    MAX("{key_column}") AS max_val
                FROM
                    "{table}";
            """

            cursor.execute(query)
            result = cursor.fetchone()

            record_count = result["record_count"] if result else 0
            min_date = result["min_val"] if result["min_val"] else "No Data"
            max_date = result["max_val"] if result["max_val"] else "No Data"
        else:
            record_count = 0  # Set record count to 0 for non-date columns

        # Fetch Table Size
        cursor.execute("SELECT pg_size_pretty(pg_total_relation_size(%s)) AS size", (table,))
        size_result = cursor.fetchone()
        table_size = size_result["size"] if size_result and "size" in size_result else "Unknown"

        # Return Data
        response = {
            "table_name": table,
            "table_size": table_size,
            "record_count": record_count,
            "min_date": min_date,
            "max_date": max_date
        }
        print(response)
        return jsonify(response)

    except Exception as e:
        print(f"SQL Error: {str(e)}")  # Debugging
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500

    finally:
        cursor.close()
        conn.close()


def is_valid_date_format(value):
    """
    Checks if the given value is in a valid date format: YYYY-MM-DD (Case 1) or DD-MM-YYYY (Case 2).
    Returns:
        - (True, 1) if format is YYYY-MM-DD
        - (True, 2) if format is DD-MM-YYYY
        - (False, None) if format is invalid
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

    

# Route to delete data
@app.route('/delete-data', methods=['POST'])
def delete_data():
    del_database = request.args.get('database')
    del_table = request.args.get('table')
    del_days = request.args.get('days')
    del_column = request.args.get('key-column')
    user_executing = request.remote_addr

    if not del_database or not del_table or not del_days or not del_column:
        return jsonify({"error": "All fields are required"}), 400

    try:
        days = int(del_days)
        conn = get_db_connection(del_database)  # Local connection
        cursor = conn.cursor()
        
        global_conn = get_db_connection("Test_Globe1")  # Global connection        
        global_cursor = global_conn.cursor()

        # Get column data type (Check table schema explicitly)
        cursor.execute("""
            SELECT data_type, table_schema 
            FROM information_schema.columns 
            WHERE table_name = %s 
            AND column_name = %s;
        """, (del_table, del_column))
        
        column_info = cursor.fetchone()
        if not column_info:
            return jsonify({"error": f"Column '{del_column}' not found in table '{del_table}'"}), 400

        column_type, table_schema = column_info
        column_type = column_type.lower()

        # Dynamically form the deletion query based on column type
        if "date" in column_type:
            delete_query = sql.SQL("""
                DELETE FROM {schema}.{table}
                WHERE {key_column} <= (SELECT MAX({key_column}) - INTERVAL %s FROM {schema}.{table})
            """).format(
                schema=sql.Identifier(table_schema),
                table=sql.Identifier(del_table),
                key_column=sql.Identifier(del_column)
            )
            cursor.execute(delete_query, (f"{days} days",))

        elif "timestamp" in column_type:
            delete_query = sql.SQL("""
                DELETE FROM {schema}.{table}
                WHERE {key_column} < (SELECT MAX({key_column}) - INTERVAL %s FROM {schema}.{table})
            """).format(
                schema=sql.Identifier(table_schema),
                table=sql.Identifier(del_table),
                key_column=sql.Identifier(del_column)
            )
            cursor.execute(delete_query, (f"{days} days",))

        elif "char" or "varchar" or "text" in column_type:  # Handles VARCHAR, TEXT, CHAR
            # Check if values in this column have valid date formats
            cursor.execute(sql.SQL("""
                SELECT DISTINCT {key_column} FROM {schema}.{table} LIMIT 5;
            """).format(
                schema=sql.Identifier(table_schema),
                table=sql.Identifier(del_table),
                key_column=sql.Identifier(del_column)
            ))

            sample_values = cursor.fetchall()
            valid_format = None

            for row in sample_values:
                is_valid, case_type = is_valid_date_format(row[0])
                if is_valid:
                    valid_format = case_type
                    break
            
            print("values for is_valid: {is_valid} ")
            print("values for case_type: {case_type} ")

            if valid_format is None:
                return jsonify({"error": f"Column '{del_column}' contains invalid date formats for deletion."}), 400

            if valid_format == 1:  # YYYY-MM-DD
                delete_query = sql.SQL("""
                    DELETE FROM {table}
                    WHERE TO_DATE({key_column}, 'YYYY-MM-DD') <= (
                    SELECT MAX(TO_DATE({key_column}, 'YYYY-MM-DD')) FROM {table}
                    ) - INTERVAL %s
                """).format(
                    table=sql.Identifier(del_table),
                    key_column=sql.Identifier(del_column)
                )
            elif valid_format == 2:  # DD-MM-YYYY
                print("inside format 2 ")
                delete_query = sql.SQL("""
                    DELETE FROM {table}
                    WHERE TO_DATE({key_column}, 'DD-MM-YYYY') <= (
                    SELECT MAX(TO_DATE({key_column}, 'DD-MM-YYYY')) FROM {table}
                    ) - INTERVAL %s
                """).format(
                    table=sql.Identifier(del_table),
                    key_column=sql.Identifier(del_column)
                )

            cursor.execute(delete_query, (f"{days} days",))

        else:
            return jsonify({"error": "Unsupported key column type"}), 400

        deleted_count = cursor.rowcount
        conn.commit()

        # Run ANALYZE
        query_analyze = sql.SQL("ANALYZE {schema}.{table};").format(
            schema=sql.Identifier(table_schema),
            table=sql.Identifier(del_table)
        )
        cursor.execute(query_analyze)
        conn.commit()

        # Run VACUUM ANALYZE outside a transaction
        conn.autocommit = True
        query_vacuum_analyze = sql.SQL("VACUUM ANALYZE {schema}.{table};").format(
            schema=sql.Identifier(table_schema),
            table=sql.Identifier(del_table)
        )
        cursor.execute(query_vacuum_analyze)
        conn.autocommit = False

        if deleted_count > 0:
            # Log deletion into delete_data_log
            log_query = sql.SQL("""
                INSERT INTO delete_data_log (server_name, database_name, table_name, record_keep_days, records_deleted, execution_date, user_executing,status)
                VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s)
            """)
            server_name = "localhost"
            global_cursor.execute(log_query, (server_name, del_database, del_table, days, deleted_count, user_executing,f'sucesfully deleted {deleted_count} records'))
            global_conn.commit()

        cursor.close()
        conn.close()
        global_cursor.close()
        global_conn.close()

        return jsonify({"message": f"Deleted {deleted_count} records from {del_table} and logged the operation."}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/schedule-data', methods=['POST'])
def schedule_data():
    del_database = request.args.get('database')
    del_table = request.args.get('table')
    del_days = request.args.get('days')
    del_column = request.args.get('key-column')
    frequency = request.args.get('frequency')
    user_executing = request.remote_addr

    if not del_database or not del_table or not del_days or not del_column or not frequency:
        return jsonify({"error": "All fields are required"}), 400

    try:
        days = int(del_days)
        frequency = int(frequency)  # Ensure frequency is an integer

        conn = get_db_connection(del_database)
        cursor = conn.cursor()

        global_conn = get_db_connection("Test_Globe1")
        global_cursor = global_conn.cursor()

        # Step 1: Check column data type
        cursor.execute("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s;
        """, (del_table, del_column))

        column_info = cursor.fetchone()
        if not column_info:
            return jsonify({"error": f"Column '{del_column}' does not exist in table '{del_table}'"}), 400

        column_type = column_info[0].lower()

        # Allowed types
        allowed_types = {"date", "timestamp", "timestamp without time zone", "timestamp with time zone"}

        is_valid_date_column = True  # Default to true

        if column_type not in allowed_types and column_type not in {"character varying", "varchar", "text"}:
            is_valid_date_column = False  # Invalid column type

        # Step 2: Validate VARCHAR column for date format
        if column_type in {"character varying", "varchar", "text"}:
            cursor.execute(f'SELECT "{del_column}" FROM "{del_table}" WHERE "{del_column}" IS NOT NULL LIMIT 10;')
            sample_values = cursor.fetchall()

            # Extract actual values
            values = [row[0] for row in sample_values if row[0]]

            # Check if all values match date format
            if not values or not all(is_valid_date_format1(str(value)) for value in values):        #format1 used
                is_valid_date_column = False

        # Step 3: Return error if column is not valid
        if not is_valid_date_column:
            return jsonify({"error": "Key column is not a date and hence cannot schedule."}), 400

        # Step 4: Check if table exists in delete_data
        check_query = sql.SQL("SELECT 1 FROM delete_data WHERE table_name = %s LIMIT 1")
        global_cursor.execute(check_query, (del_table,))
        table_exists = global_cursor.fetchone()

        print('Frequency:', frequency)  # Debugging purpose

        if table_exists:
            update_query = sql.SQL("""
                UPDATE delete_data 
                SET record_keep_days = %s, key_column = %s, frequency = %s, run_date = NOW(), 
                    next_run_date = NOW() + (%s || ' days')::INTERVAL
                WHERE table_name = %s;
            """)
            global_cursor.execute(update_query, (days, del_column, frequency, str(frequency), del_table))
            global_conn.commit()

        else:
            insert_query = sql.SQL("""
                INSERT INTO delete_data (server_name, database_name, table_name, key_column, record_keep_days, frequency, run_date, next_run_date)
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW() + (%s || ' days')::INTERVAL)
            """)
            server_name = "localhost"
            global_cursor.execute(insert_query, (server_name, del_database, del_table, del_column, days, frequency, str(frequency)))
            global_conn.commit()

        # Close connections
        cursor.close()
        conn.close()
        global_cursor.close()
        global_conn.close()

        return jsonify({"message": "Scheduled the operation successfully."}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/master_table')
def master_table():
    return render_template('master_table.html')  # This will load the table

@app.route('/get_delete_data', methods=['GET'])
def get_delete_data():
    try:
        conn = get_db_connection("Test_Globe1")  # Directly use Test_Globe1
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Fetch all records from delete_data
        query = '''SELECT * FROM delete_data 
        ORDER BY   table_name, run_date;'''     
        cursor.execute(query)
        records = cursor.fetchall()

        cursor.close()
        conn.close()
        print(f"reccords are {records}")
        return jsonify(records)  # Send data to frontend

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    


# Route to serve the Delete Data Log page
@app.route('/delete_data_log')
def delete_data_log():
    return render_template('delete_data_log.html')

# API to fetch Delete Data Log records
@app.route('/get_delete_data_log')
def get_delete_data_log():
    try:
        conn = get_db_connection("Test_Globe1")  # Directly use Test_Globe
        cursor = conn.cursor(cursor_factory=RealDictCursor)


        # Fetch data from the delete_data_log table
        query='''SELECT * FROM delete_data_log  
         ORDER BY execution_date DESC ;'''
        cursor.execute(query)
        records = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify(records)  # Send data to frontend

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    


@app.route("/report_statistics")
def report_statistics():
    return render_template("report_statistics.html")

@app.route("/get_report_statistics")
def get_report_statistics():
    connection = get_db_connection("Test_Delete")  # Ensure this function is correctly implemented
    cursor = connection.cursor()
    
    query = """
    SELECT s.relname AS table_name, 
           c.reltuples AS row_count,
           s.last_analyze, 
           pg_size_pretty(pg_relation_size(c.oid)) AS size
    FROM pg_stat_all_tables s 
    JOIN pg_class c ON s.relname = c.relname
    WHERE s.schemaname = 'public' 
    AND c.reltuples > 0
    ORDER BY pg_relation_size(c.oid) DESC;
    """

    cursor.execute(query)
    data = cursor.fetchall()
    
    cursor.close()
    connection.close()

    report_data = [
        {
            "table_name": row[0], 
            "row_count": int(row[1]), 
            "last_analyze": row[2] if row[2] else "N/A", 
            "size": row[3]
        }
        for row in data
    ]

    return jsonify(report_data)


@app.route('/scheduled_execution')
def scheduled_execution():
    return render_template('scheduled_execution.html')  # This will load the table

@app.route('/get_schedule_data',methods=['GET'])
def get_schedule_data():
    try:
        conn = get_db_connection("Test_Globe1")  # Directly use Test_Globe1
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Fetch all records from delete_data
        query = '''SELECT *  FROM delete_data where next_run_date >=  CAST(NOW() AS  date)
        ORDER BY    next_run_date,table_name;'''
        print(f"QUERY : {query}")
        cursor.execute(query)
        records = cursor.fetchall()

        cursor.close()
        conn.close()
        print(f"records are {records}")
        return jsonify(records)  # Send data to frontend

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    



@app.route('/database_statistics')
def database_statistics():
    return render_template('database_statistics.html')  

@app.route('/fetch_db_sessions', methods=['GET'])
def fetch_db_sessions():
    """Fetch database-wise size, table count, and session count."""
    try:
        results = []
        
        for db in DATABASES:
            conn = get_db_connection(db)
            cur = conn.cursor()

            # Get database size
            cur.execute(f"SELECT pg_size_pretty(pg_database_size('{db}'));")
            db_size = cur.fetchone()[0]

            # Get session count
            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s;", (db,))
            session_count = cur.fetchone()[0]

            # Get table count
            cur.execute("SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema');")
            table_count = cur.fetchone()[0]
            
        

            results.append({
                "database_name": db,
                "database_size": db_size,
                "session_count": session_count,
                "table_count": table_count
            })

            cur.close()
            conn.close()

        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/get_database_stats', methods=['GET'])
def fetch_database_stats():
    """Fetch total database size, total tables, and active sessions."""
    try:
        conn = get_db_connection('Test_Delete')
        cur = conn.cursor()

        # Get total database size
        cur.execute("SELECT pg_size_pretty(sum(pg_database_size(datname))) FROM pg_database;")
        total_size = cur.fetchone()[0]

        # Get total session count
        cur.execute("SELECT count(*) FROM pg_stat_activity;")
        total_sessions = cur.fetchone()[0]

        # Get total tables from frontend (precomputed in JS)
        total_tables = request.args.get("total_tables", 0, type=int)

        cur.close()
        conn.close()

        return jsonify({
            "total_size": total_size,
            "total_tables": total_tables,
            "sessions": total_sessions
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500




if __name__ == '__main__':
    app.run(debug=True,port=5008)
