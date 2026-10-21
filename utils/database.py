import logging
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql


# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
# The application-level logging configuration is initialized centrally.
# This module only creates a logger for database-related messages.
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Project Configuration
# ---------------------------------------------------------------------------

# Resolve the project root directory.
# This allows the .env file to be loaded consistently regardless of
# the directory from which the application is started.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load environment variables from the project's .env file.
load_dotenv(PROJECT_ROOT / ".env")


# ---------------------------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------------------------

# Database connection details are loaded from environment variables.
# Sensitive values such as the password are never written to logs.
def get_db_config() -> dict[str, str | int]:
    """Read database settings when a database operation is requested."""
    return {
        "host": os.environ["DB_HOST"],
        "port": int(os.environ["DB_PORT"]),
        "database": os.environ["DB_NAME"],
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
    }

# Directory used for CSV/data files.
CSV_DIR = os.getenv("CSV_DIR", "data")


# ---------------------------------------------------------------------------
# Database Utility
# ---------------------------------------------------------------------------

class DatabaseUtil:
    """
    Utility class for PostgreSQL database operations.

    Provides functionality to:
    - Establish and close database connections.
    - Retrieve schema and table metadata.
    - Retrieve sample table records.
    - Execute SQL queries.
    """

    def __init__(self, db_config):
        """
        Initialize the database utility and establish a connection.

        Args:
            db_config: Dictionary containing PostgreSQL connection settings.
        """
        self.db_config = db_config

        logger.info("Initializing database connection")

        try:
            self.connection = psycopg2.connect(**db_config)
            logger.info("Database connection established successfully")
        except Exception as e:
            logger.error("Failed to establish database connection: %s", e)
            raise

    def schema_details(self, schema_name):
        """
        Retrieve schema metadata, table structures, and sample records.

        Args:
            schema_name: PostgreSQL schema name.

        Returns:
            A formatted string containing:
            - Table names
            - Column names
            - Data types
            - Up to 5 sample records per table
        """
        logger.info("Fetching schema details for schema: %s", schema_name)

        schema_info = [f"Schema: {schema_name}\n"]

        try:
            with self.connection.cursor() as cursor:

                # Retrieve all tables available in the requested schema.
                cursor.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    ORDER BY table_name;
                    """,
                    (schema_name,),
                )

                table_names = [row[0] for row in cursor.fetchall()]

                logger.info(
                    "Found %d table(s) in schema: %s",
                    len(table_names),
                    schema_name,
                )

                # Retrieve column metadata and sample data for each table.
                for table_name in table_names:

                    logger.debug(
                        "Processing table metadata: %s.%s",
                        schema_name,
                        table_name,
                    )

                    schema_info.append(f"\nTable: {table_name}\n")

                    # Retrieve column names and data types.
                    cursor.execute(
                        """
                        SELECT column_name, data_type
                        FROM information_schema.columns
                        WHERE table_schema = %s
                          AND table_name = %s
                        ORDER BY ordinal_position;
                        """,
                        (schema_name, table_name),
                    )

                    for column_name, data_type in cursor.fetchall():
                        schema_info.append(
                            f"  Column: {column_name}, Data Type: {data_type}\n"
                        )

                    # Retrieve a small sample of records.
                    # Identifier() is used to safely construct dynamic
                    # schema/table references.
                    cursor.execute(
                        sql.SQL("SELECT * FROM {}.{} LIMIT 5;").format(
                            sql.Identifier(schema_name),
                            sql.Identifier(table_name),
                        )
                    )

                    schema_info.append(
                        f"Sample Data from {table_name}:\n"
                    )

                    sample_rows = cursor.fetchall()

                    schema_info.extend(
                        f"  {row}\n"
                        for row in sample_rows
                    )

                    logger.debug(
                        "Retrieved %d sample record(s) from %s.%s",
                        len(sample_rows),
                        schema_name,
                        table_name,
                    )

            logger.info(
                "Schema details retrieved successfully for: %s",
                schema_name,
            )

            return "".join(schema_info)

        except Exception as e:
            logger.error(
                "Failed to retrieve schema details for '%s': %s",
                schema_name,
                e,
            )
            raise

    def close(self):
        """
        Close the active database connection.
        """
        if self.connection and not self.connection.closed:
            logger.info("Closing database connection")
            self.connection.close()
            logger.info("Database connection closed successfully")
        else:
            logger.debug("Database connection is already closed")

    def execute_sql_query(self, query):
        """
        Execute a SQL query using a new database connection.

        Args:
            query: SQL query string to execute.

        Returns:
            String representation of query results when the query returns
            rows. Returns None when no result set is available or execution
            fails.
        """
        logger.info("Executing SQL query")

        connection = None
        cursor = None

        try:
            # Create a separate connection for query execution.
            connection = psycopg2.connect(**self.db_config)
            cursor = connection.cursor()

            logger.debug("SQL query connection established")

            cursor.execute(query)

            # cursor.description is available when the query returns rows,
            # such as SELECT statements.
            if cursor.description:
                result = cursor.fetchall()

                connection.commit()

                logger.info(
                    "SQL query executed successfully; %d row(s) returned",
                    len(result),
                )

                return str(result)

            # Queries without a result set do not return data.
            logger.info("SQL query executed successfully with no result set")

            connection.commit()

            return None

        except Exception as e:
            # Log the error without logging the complete SQL query.
            # This prevents potentially sensitive SQL/data from appearing
            # in application logs.
            logger.error("Error executing SQL query: %s", e)

            # Roll back any incomplete transaction.
            if connection and not connection.closed:
                connection.rollback()
                logger.debug("Database transaction rolled back")

            return None

        finally:
            # Always close the cursor after query execution.
            if cursor and not cursor.closed:
                cursor.close()
                logger.debug("SQL cursor closed")

            # Always close the temporary connection.
            if connection and not connection.closed:
                connection.close()
                logger.debug("SQL query connection closed")


# ---------------------------------------------------------------------------
# Standalone Test
# ---------------------------------------------------------------------------
#
# Uncomment the following section when you want to test this utility
# independently from the main application.
#
# def main():
#     database = DatabaseUtil(DB_CONFIG)
#
#     try:
#         schema_info = database.schema_details("public")
#
#         output_path = PROJECT_ROOT / "schema_info.txt"
#         output_path.write_text(schema_info, encoding="utf-8")
#
#         logger.info(
#             "Schema information written successfully to: %s",
#             output_path,
#         )
#
#     finally:
#         database.close()
#
#
# if __name__ == "__main__":
#     main()