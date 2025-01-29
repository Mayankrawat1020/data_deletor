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
    database = request.args.get('database')
    table = request.args.get('table')
    days = request.form.get('days')
    column = request.args.get('key-column')
    
    
   # print(f"Parameters at delete table- details  received - Database: {database}, Table: {table},column:{column}, days: {days}")

    if not database or not table or not days:
        return jsonify({"error": "All fields are required"}), 400

    try:
        days=int(days)
        conn = get_db_connection(database)
        cursor = conn.cursor()
        print("query in process")
        deletion_query = sql.SQL("""
    DELETE FROM {table}
    WHERE {column} NOT BETWEEN 
        (SELECT (MAX({column})-  {days}) FROM {table}) 
        AND 
        (SELECT MAX({column}) FROM {table})
""").format(
    table=sql.Identifier(table),
    column=sql.Identifier(column)
)

        print(f"deletion queryu:",deletion_query)
        
        cursor.execute(deletion_query, (f'{int(days)} days',))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": "Data deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
