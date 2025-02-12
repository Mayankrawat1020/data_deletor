from flask import Flask, request, jsonify, render_template
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql

app = Flask(__name__)

# Database configurations
DATABASES = {
    "db1": {
        "host": "localhost",
        "port": 5432,
        "database": "postgres",
        "user": "postgres",
        "password": "mayank"
    }
}

# Utility function to get a database connection
def get_db_connection(db_name):
    if db_name not in DATABASES:
        raise ValueError(f"Database configuration for {db_name} not found.")
    config = DATABASES[db_name]
    return psycopg2.connect(
        host=config["host"],
        port=config["port"],
        database=config["database"],
        user=config["user"],
        password=config["password"]
    )

@app.route('/')
def index():
    return render_template('index2.html')

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
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s;", (table,))
        columns = [row['column_name'] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return jsonify(columns)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to fetch table details (size, record count, min/max date)
@app.route('/get-table-details', methods=['GET'])
def get_table_details():
    database = request.args.get('database')
    table = request.args.get('table')
    column = request.args.get('key-column')

    # Debugging log
    print(f"Parameters at get table- details  received - Database: {database}, Table: {table}, Column: {column}")


    if not database or not table or not column:
        return jsonify({"error": "Database, table, and column are required"}), 400

    try:
        conn = get_db_connection(database)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get table size
        cursor.execute("SELECT pg_size_pretty(pg_total_relation_size(%s)) AS size;", (table,))
        table_size = cursor.fetchone()["size"]

        # Get record count
        record_count_query = sql.SQL("SELECT COUNT(*) AS count FROM {table}").format(
            table=sql.Identifier(table)
        )
        cursor.execute(record_count_query)
        record_count = cursor.fetchone()["count"]

        # Get min and max dates
        min_max_query = sql.SQL("SELECT MIN({column}) AS min_date, MAX({column}) AS max_date FROM {table}").format(
            column=sql.Identifier(column),
            table=sql.Identifier(table)
        )
        cursor.execute(min_max_query)
        date_info = cursor.fetchone()

        cursor.close()
        conn.close()

        return jsonify({
            "table_size": table_size,
            "record_count": record_count,
            "min_date": date_info["min_date"],
            "max_date": date_info["max_date"]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to delete data
@app.route('/delete-data', methods=['POST'])
def delete_data():
    del_database = request.args.get('database')
    del_table = request.args.get('table')
    del_days = request.args.get('days')
    del_column = request.args.get('key-column')
    user_executing = request.remote_addr

    if not del_database or not del_table or not del_days:
        return jsonify({"error": "All fields are required"}), 400

    try:
        days = int(del_days)
        conn = get_db_connection(del_database)
        cursor = conn.cursor()

        # Deletion query (Not Modified)
        deletion_query = sql.SQL("""
            DELETE FROM {table}
            WHERE {column} NOT BETWEEN 
                (SELECT (MAX({column}) - {days}) FROM {table}) 
                AND 
                (SELECT MAX({column}) FROM {table})
        """).format(
            table=sql.Identifier(del_table),
            column=sql.Identifier(del_column),
            days=sql.Literal(days)
        )

        cursor.execute(deletion_query)
        deleted_count = cursor.rowcount
        conn.commit()

        if deleted_count > 0:
            # Log deletion into delete_data_log
            log_query = sql.SQL("""
                INSERT INTO delete_data_log (server_name, database_name, table_name, record_keep_days, records_deleted, execution_date, user_executing)
                VALUES (%s, %s, %s, %s, %s, NOW(), %s)
            """)

            server_name = "localhost"
            cursor.execute(log_query, (server_name, del_database, del_table, days, deleted_count, user_executing))
            conn.commit()

        # Check if table already exists in delete_data
        check_query = sql.SQL("SELECT 1 FROM delete_data WHERE table_name = %s LIMIT 1")
        cursor.execute(check_query, (del_table,))
        table_exists = cursor.fetchone()

        if not table_exists:
            insert_query = sql.SQL("""
                INSERT INTO delete_data (server_name, database_name, table_name, record_keep_days, frequency, run_date, next_run_date)
                VALUES (%s, %s, %s, %s, %s, NOW(), %s)
            """)

            frequency = 1
            next_run_date = None
            cursor.execute(insert_query, (server_name, del_database, del_table, days, frequency, next_run_date))
            conn.commit()

        cursor.close()
        conn.close()

        return jsonify({"message": f"Deleted {deleted_count} records from {del_table} and logged the operation."}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
