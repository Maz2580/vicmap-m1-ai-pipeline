"""
Database Helper for InfoProd SQL Server
Connects to InfoProd database to query property, parcel, and rates data
"""
import logging
import pyodbc
from typing import List, Dict, Optional, Tuple
import pandas as pd
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class InfoProdDatabaseHelper:
    """
    Helper class for querying InfoProd SQL Server database
    Specifically designed for M1 validation using property, parcel, and rates data
    """
    
    def __init__(self, server: str = None, username: str = None, 
                 password: str = None, database: str = None):
        """
        Initialize database connection
        
        Args:
            server: SQL Server hostname (defaults to DB_SERVER env var)
            username: Database username (defaults to DB_USERNAME env var)
            password: Database password (defaults to DB_PASSWORD env var)
            database: Database name (defaults to DB_DATABASE env var)
        """
        # Load from environment variables if not provided.
        # All 4 values must be configured in .env — defaults are empty so the
        # connection fails loudly if the adopter has not set them up yet.
        self.server = server or os.getenv('DB_SERVER', '')
        self.username = username or os.getenv('DB_USERNAME', '')
        self.password = password or os.getenv('DB_PASSWORD', '')
        self.database = database or os.getenv('DB_DATABASE', 'InfoProd')
        
        self.logger = logging.getLogger('DatabaseHelper')
        
        # Connection string for SQL Server
        self.connection_string = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={self.server};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password}"
        )
        
        # Cache for table exploration
        self.tables_cache = {}
        self.property_tables = []  # List of property tables
        self.parcel_tables = []     # List of parcel tables
        self.rates_tables = []      # List of rates tables
        self.property_table = None  # Primary property table
        self.parcel_table = None    # Primary parcel table
        self.rates_table = None     # Primary rates table
        
        # Try to connect and explore database on initialization
        self._explore_database()
    
    def _get_connection(self):
        """Get database connection"""
        try:
            connection = pyodbc.connect(self.connection_string)
            return connection
        except pyodbc.Error as e:
            self.logger.error(f"Failed to connect to database: {e}")
            raise
    
    def _explore_database(self):
        """Explore database structure to find relevant tables"""
        try:
            connection = self._get_connection()
            cursor = connection.cursor()
            
            # Get all table names
            tables_query = """
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """
            
            cursor.execute(tables_query)
            rows = cursor.fetchall()
            
            all_tables = []
            for row in rows:
                schema, table = row
                all_tables.append(f"{schema}.{table}")
            
            self.logger.info(f"Found {len(all_tables)} tables in database")
            
            # Collect ALL relevant tables, not just the first one
            # Property tables
            property_keywords = ['property', 'prop', 'PTH_PROP']
            parcel_keywords = ['parcel', 'PTH_PAR']
            rates_keywords = ['rate', 'assessment', 'valuation']
            
            # Priority tables (will be checked first)
            priority_property_tables = [
                'Infodbo.Property',   # Main property table - MUST be first
                'dbo.PTH_PROP_CUR',  # Has TPKLPAPROP column
                'Infodbo.Property_Customer',  # Has TPKLPAPROP column
                'Infodbo.GIS_property',
                'Infodbo.Property_Details',
                'Infodbo.Property_Info'
            ]
            
            priority_parcel_tables = [
                'Infodbo.Property_Parcels',
                'Infodbo.Parcel',
                'dbo.PTH_PARCEL_CUR'
            ]
            
            priority_rates_tables = [
                'Infodbo.Rate_Assessment',
                'Infodbo.Rate_Activity',
                'Infodbo.Property_Assessment_Links',
                'Infodbo.Application_Value_Band'
            ]
            
            # First pass: Find Infodbo.Property specifically
            for table in all_tables:
                if table == 'Infodbo.Property':
                    self.property_table = table
                    self.logger.info(f"Selected primary property table: {table}")
                    break
            
            # Second pass: Collect all property tables
            for table in all_tables:
                table_lower = table.lower()
                schema_table = table.split('.')
                table_only = schema_table[-1] if len(schema_table) > 1 else table
                
                # Check for property tables
                is_property = any(keyword.lower() in table_lower for keyword in property_keywords)
                is_priority_property = any(priority in table for priority in priority_property_tables)
                
                if is_property:
                    self.property_tables.append(table)
                    # Select priority table if Infodbo.Property not found
                    if is_priority_property and not self.property_table:
                        self.property_table = table
                        self.logger.info(f"Selected primary property table: {table}")
                
                # Check for parcel tables
                is_parcel = any(keyword.lower() in table_lower for keyword in parcel_keywords)
                is_priority_parcel = any(priority in table for priority in priority_parcel_tables)
                
                if is_parcel:
                    self.parcel_tables.append(table)
                    if is_priority_parcel and not self.parcel_table:
                        self.parcel_table = table
                        self.logger.info(f"Selected primary parcel table: {table}")
                
                # Check for rates tables
                is_rates = any(keyword.lower() in table_lower for keyword in rates_keywords)
                is_priority_rates = any(priority in table for priority in priority_rates_tables)
                
                if is_rates:
                    self.rates_tables.append(table)
                    if is_priority_rates and not self.rates_table:
                        self.rates_table = table
                        self.logger.info(f"Selected primary rates table: {table}")
            
            # Set primary tables if not already set
            if not self.property_table and self.property_tables:
                self.property_table = self.property_tables[0]
                self.logger.info(f"Using first property table: {self.property_table}")
            
            if not self.parcel_table and self.parcel_tables:
                self.parcel_table = self.parcel_tables[0]
                self.logger.info(f"Using first parcel table: {self.parcel_table}")
            
            if not self.rates_table and self.rates_tables:
                self.rates_table = self.rates_tables[0]
                self.logger.info(f"Using first rates table: {self.rates_table}")
            
            # Log all found tables
            self.logger.info(f"Found {len(self.property_tables)} property tables")
            self.logger.info(f"Found {len(self.parcel_tables)} parcel tables")
            self.logger.info(f"Found {len(self.rates_tables)} rates tables")
            
            # Store all tables for debugging
            self.tables_cache = {
                'all_tables': all_tables,
                'property_table': self.property_table,
                'parcel_table': self.parcel_table,
                'rates_table': self.rates_table,
                'all_property_tables': self.property_tables,
                'all_parcel_tables': self.parcel_tables,
                'all_rates_tables': self.rates_tables
            }
            
            cursor.close()
            connection.close()
            
        except Exception as e:
            self.logger.error(f"Error exploring database: {e}")
            self.logger.warning("Database exploration failed. Some features may not work.")
    
    def get_table_info(self, table_name: str) -> Dict:
        """
        Get information about a specific table
        
        Args:
            table_name: Name of the table (e.g., 'Property' or 'schema.Property')
            
        Returns:
            Dictionary with table information including columns and sample data
        """
        try:
            connection = self._get_connection()
            
            # Get column information
            columns_query = f"""
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = '{table_name.split('.')[1] if '.' in table_name else table_name}'
                ORDER BY ORDINAL_POSITION
            """
            
            columns_df = pd.read_sql(columns_query, connection)
            
            # Get sample data (first 10 rows)
            sample_query = f"SELECT TOP 10 * FROM [{table_name}]"
            sample_df = pd.read_sql(sample_query, connection)
            
            connection.close()
            
            return {
                'columns': columns_df.to_dict('records'),
                'sample_data': sample_df.to_dict('records')
            }
            
        except Exception as e:
            self.logger.error(f"Error getting table info for {table_name}: {e}")
            return {'columns': [], 'sample_data': []}
    
    def find_property_by_propnum(self, propnum: str, format: str = None, check_new_properties: bool = True) -> Optional[Dict]:
        """
        Find property by property number (TPKLPAPROP)
        
        Args:
            propnum: Property number to search for
            format: Optional format parameter (e.g., 'TPKLPAPROP')
            check_new_properties: If True, also checks for Status='C' properties (new, not yet in GIS)
            
        Returns:
            Property data dictionary or None if not found
        """
        if not self.property_table:
            self.logger.error("Property table not identified")
            return None
        
        try:
            connection = self._get_connection()
            
            # Try different column name variations for property number
            # Based on actual database schema
            propnum_columns = ['TPKLPAPROP', 'tpklpaprop', 'PROPNUM', 'PropertyNumber', 'PROP_NUM', 'prop_num', 'PropNum', 'property_num', 'propnum']
            
            query_success = False
            result = None
            
            # First, try to find in standard property tables (Status not 'C')
            for col in propnum_columns:
                try:
                    query = f"SELECT TOP 1 * FROM [{self.property_table}] WHERE [{col}] = ?"
                    cursor = connection.cursor()
                    cursor.execute(query, (propnum,))
                    row = cursor.fetchone()
                    
                    if row:
                        # Convert row to dictionary
                        columns = [desc[0] for desc in cursor.description]
                        result = dict(zip(columns, row))
                        query_success = True
                        cursor.close()
                        break
                    cursor.close()
                    
                except Exception as e:
                    continue
            
            # If not found and check_new_properties is True, check for new properties (Status='C')
            if not query_success and check_new_properties:
                self.logger.info(f"Property {propnum} not found in standard tables, checking for new properties (Status='C')")
                
                try:
                    # Query for Status='C' in Infodbo.Property
                    # Use TPKLPAPROP column instead of propnum
                    query = "SELECT TOP 1 * FROM [Infodbo].[Property] WHERE TPKLPAPROP = ? AND Status = 'C'"
                    cursor = connection.cursor()
                    cursor.execute(query, (propnum,))
                    row = cursor.fetchone()
                    
                    if not row:
                        # Also try with propnum column if TPKLPAPROP didn't work
                        query = "SELECT TOP 1 * FROM [Infodbo].[Property] WHERE propnum = ? AND Status = 'C'"
                        cursor.execute(query, (propnum,))
                        row = cursor.fetchone()
                    
                    if row:
                        columns = [desc[0] for desc in cursor.description]
                        result = dict(zip(columns, row))
                        result['_is_new_property'] = True
                        result['_status'] = 'C'
                        query_success = True
                        self.logger.info(f"Found new property (Status='C') in Infodbo.Property")
                        cursor.close()
                    
                except Exception as e:
                    self.logger.warning(f"Could not check for new properties: {e}")
                    pass
            
            # If still not found, try fuzzy search
            if not query_success:
                self.logger.warning(f"Property not found for propnum: {propnum}")
                # Try fuzzy search
                for col in propnum_columns:
                    try:
                        query = f"SELECT TOP 10 * FROM [{self.property_table}] WHERE [{col}] LIKE ?"
                        cursor = connection.cursor()
                        cursor.execute(query, (f'%{propnum}%',))
                        rows = cursor.fetchall()
                        
                        if rows:
                            columns = [desc[0] for desc in cursor.description]
                            result = dict(zip(columns, rows[0]))
                            self.logger.info(f"Found property using fuzzy search on {col}")
                            query_success = True
                            cursor.close()
                            break
                        cursor.close()
                        
                    except Exception as e:
                        continue
            
            connection.close()
            return result if query_success else None
            
        except Exception as e:
            self.logger.error(f"Error finding property by propnum {propnum}: {e}")
            return None
    
    def find_address_relationships(self, address_data: Dict[str, str]) -> List[Dict]:
        """
        Find all records related to an address
        
        Args:
            address_data: Dictionary with address components (road_name, locality_name, house_number, etc.)
            
        Returns:
            List of related records from database
        """
        if not self.property_table:
            self.logger.error("Property table not identified")
            return []
        
        try:
            connection = self._get_connection()
            results = []
            
            # Build query based on available address components
            road_name = address_data.get('road_name', '').upper()
            locality = address_data.get('locality_name', '').upper()
            house_num = address_data.get('house_number_1', '')
            
            # Common column name variations for address fields
            road_columns = ['ROAD_NAME', 'ROADNAME', 'StreetName', 'ROAD', 'Street']
            locality_columns = ['LOCALITY_NAME', 'LOCALITYNAME', 'Suburb', 'LOCALITY', 'SUBURB']
            house_columns = ['HOUSE_NUMBER', 'HOUSENUM', 'HouseNum', 'NUMBER']
            
            query_conditions = []
            params = []
            
            # Add conditions based on available data
            for col in road_columns:
                if road_name:
                    query_conditions.append(f"[{col}] = ?")
                    params.append(road_name)
                    break
            
            for col in locality_columns:
                if locality:
                    if not query_conditions:
                        query_conditions.append(f"[{col}] = ?")
                    else:
                        query_conditions[-1] += f" AND [{col}] = ?"
                    params.append(locality)
                    break
            
            for col in house_columns:
                if house_num:
                    if not query_conditions:
                        query_conditions.append(f"[{col}] = ?")
                    else:
                        query_conditions[-1] += f" AND [{col}] = ?"
                    params.append(house_num)
                    break
            
            if query_conditions:
                query = f"SELECT TOP 50 * FROM [{self.property_table}] WHERE {' AND '.join(query_conditions)}"
                
                try:
                    df = pd.read_sql(query, connection, params=params)
                    results = df.to_dict('records')
                    
                except Exception as e:
                    self.logger.warning(f"Error querying address relationships: {e}")
            
            connection.close()
            return results
            
        except Exception as e:
            self.logger.error(f"Error finding address relationships: {e}")
            return []
    
    def get_rates_data(self, propnum: str) -> Optional[Dict]:
        """
        Get rates/valuation data for a property
        
        Args:
            propnum: Property number (TPKLPAPROP)
            
        Returns:
            Rates data dictionary or None if not found
        """
        if not self.rates_table:
            self.logger.warning("Rates table not identified, skipping rates lookup")
            return None
        
        try:
            connection = self._get_connection()
            
            # Try to find rates data linked by property number
            propnum_columns = ['TPKLPAPROP', 'PROPNUM', 'PropertyNumber', 'PROP_NUM']
            
            for col in propnum_columns:
                try:
                    query = f"SELECT TOP 1 * FROM [{self.rates_table}] WHERE [{col}] = ?"
                    cursor = connection.cursor()
                    cursor.execute(query, (propnum,))
                    row = cursor.fetchone()
                    
                    if row:
                        columns = [desc[0] for desc in cursor.description]
                        result = dict(zip(columns, row))
                        cursor.close()
                        connection.close()
                        return result
                    
                    cursor.close()
                    
                except Exception as e:
                    continue
            
            connection.close()
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting rates data for propnum {propnum}: {e}")
            return None
    
    def validate_property_exists(self, propnum: str) -> Tuple[bool, List[str]]:
        """
        Validate if a property exists in the database
        
        Args:
            propnum: Property number to validate
            
        Returns:
            Tuple of (exists, issues_list)
        """
        property_data = self.find_property_by_propnum(propnum)
        
        if property_data:
            return True, []
        else:
            return False, [f"Property {propnum} not found in InfoProd database"]
    
    def get_all_tables(self) -> List[str]:
        """Get list of all tables in the database"""
        return self.tables_cache.get('all_tables', [])
    
    def get_database_summary(self) -> Dict:
        """Get summary of database exploration"""
        return self.tables_cache
    
    def find_property_in_all_tables(self, propnum: str) -> Optional[Dict]:
        """
        Search for property in ALL property tables (not just the primary one)
        
        Args:
            propnum: Property number to search for
            
        Returns:
            Property data from the first matching table, or None
        """
        self.logger.info(f"Searching for property {propnum} in {len(self.property_tables)} tables")
        
        # Try primary table first
        if self.property_table:
            result = self.find_property_by_propnum(propnum)
            if result:
                self.logger.info(f"Found in primary table: {self.property_table}")
                return result
        
        # Try other property tables
        for table in self.property_tables:
            if table == self.property_table:
                continue
            
            try:
                self.logger.info(f"Trying table: {table}")
                connection = self._get_connection()
                
                # Try different column names - TPKLPAPROP first (correct column name)
                for col in ['TPKLPAPROP', 'tpklpaprop', 'PROPNUM', 'PropertyNumber', 'PROP_NUM', 'propnum']:
                    try:
                        # Also check for Status='C' if this is the Infodbo.Property table
                        if 'Infodbo.Property' in table:
                            # First try with Status check
                            query = f"SELECT TOP 1 * FROM [{table}] WHERE [{col}] = ?"
                            cursor = connection.cursor()
                            cursor.execute(query, (propnum,))
                            row = cursor.fetchone()
                            
                            if not row:
                                # Try with Status='C' for new properties
                                query = f"SELECT TOP 1 * FROM [{table}] WHERE [{col}] = ? AND Status = 'C'"
                                cursor.execute(query, (propnum,))
                                row = cursor.fetchone()
                        else:
                            # Standard query for other tables
                            query = f"SELECT TOP 1 * FROM [{table}] WHERE [{col}] = ?"
                            cursor = connection.cursor()
                            cursor.execute(query, (propnum,))
                            row = cursor.fetchone()
                        
                        if row:
                            columns = [desc[0] for desc in cursor.description]
                            result = dict(zip(columns, row))
                            result['_source_table'] = table
                            cursor.close()
                            connection.close()
                            self.logger.info(f"Found in table: {table} using column: {col}")
                            return result
                        cursor.close()
                        
                    except Exception as e:
                        self.logger.debug(f"Error querying {table} with {col}: {e}")
                        continue
                
                connection.close()
                
            except Exception as e:
                self.logger.warning(f"Error querying table {table}: {e}")
                continue
        
            self.logger.warning(f"Property {propnum} not found in any property tables")
            return None
    
    def find_property_by_address_and_plan(self, address_data: Dict[str, str], plan_number: str = None, plan_key: int = None) -> Optional[Dict]:
        """
        Find property by address, plan number, and plan key (for new properties)
        
        Args:
            address_data: Dictionary with address components (road_name, locality_name, house_number, etc.)
            plan_number: Plan number (e.g., 'PS900126')
            plan_key: Plan key (optional)
            
        Returns:
            Property data dictionary or None if not found
        """
        try:
            connection = self._get_connection()
            
            # Build query for Infodbo.Property with Status='C'
            conditions = []
            params = []
            
            # Check for plan number
            if plan_number:
                conditions.append("plan_number = ? OR Plan_Number = ?")
                params.extend([plan_number, plan_number])
            
            # Check for plan key
            if plan_key:
                conditions.append("plan_key = ? OR Plan_Key = ?")
                params.extend([plan_key, plan_key])
            
            # Check for address components
            if address_data.get('road_name'):
                conditions.append("(road_name = ? OR Road_Name = ? OR Formatted_Address LIKE ?)")
                road_name = address_data['road_name'].upper()
                params.extend([road_name, road_name, f'%{road_name}%'])
            
            if address_data.get('locality_name'):
                conditions.append("(locality_name = ? OR Locality_Name = ?)")
                locality = address_data['locality_name'].upper()
                params.extend([locality, locality])
            
            if address_data.get('house_number_1'):
                conditions.append("(house_number_1 = ? OR House_Number_1 = ?)")
                house_num = address_data['house_number_1']
                params.extend([house_num, house_num])
            
            if not conditions:
                self.logger.warning("No search criteria provided")
                return None
            
            # Add Status='C' to find new properties
            conditions.append("Status = 'C'")
            
            where_clause = " AND ".join(conditions)
            query = f"SELECT TOP 1 * FROM [Infodbo.Property] WHERE {where_clause}"
            
            self.logger.info(f"Searching for new property with query: {where_clause}")
            
            cursor = connection.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()
            
            if row:
                columns = [desc[0] for desc in cursor.description]
                result = dict(zip(columns, row))
                result['_is_new_property'] = True
                result['_status'] = 'C'
                cursor.close()
                connection.close()
                self.logger.info(f"Found new property (Status='C')")
                return result
            
            cursor.close()
            connection.close()
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding property by address and plan: {e}")
            return None
