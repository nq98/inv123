"""
NetSuite Event Tracking Service
Comprehensive bidirectional event tracking between our system and NetSuite
"""

from google.cloud import bigquery
from datetime import datetime, timedelta
import json
from typing import Dict, List, Optional, Any
import traceback

class NetSuiteEventTracker:
    def __init__(self, project_id='invoicereader-477008'):
        self.project_id = project_id
        self.client = bigquery.Client(project=project_id)
        self.events_table = f"{project_id}.vendors_ai.netsuite_events"
        self._ensure_events_table()
    
    def _ensure_events_table(self):
        """Create comprehensive NetSuite events table if it doesn't exist"""
        try:
            # Check if table exists
            self.client.get_table(self.events_table)
            print(f"✓ NetSuite events table {self.events_table} already exists")
        except:
            # Create table with comprehensive schema
            schema = [
                bigquery.SchemaField("event_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("direction", "STRING", mode="REQUIRED"),  # OUTBOUND or INBOUND
                bigquery.SchemaField("event_type", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("event_category", "STRING", mode="REQUIRED"),  # VENDOR, INVOICE, BILL, PAYMENT
                bigquery.SchemaField("status", "STRING", mode="REQUIRED"),  # SUCCESS, FAILED, PENDING
                bigquery.SchemaField("entity_type", "STRING"),
                bigquery.SchemaField("entity_id", "STRING"),
                bigquery.SchemaField("netsuite_id", "STRING"),
                bigquery.SchemaField("action", "STRING"),  # CREATE, UPDATE, DELETE, SYNC, APPROVE, REJECT
                bigquery.SchemaField("request_data", "JSON"),
                bigquery.SchemaField("response_data", "JSON"),
                bigquery.SchemaField("error_message", "STRING"),
                bigquery.SchemaField("duration_ms", "INT64"),
                bigquery.SchemaField("user", "STRING"),
                bigquery.SchemaField("metadata", "JSON"),
            ]
            
            table = bigquery.Table(self.events_table, schema=schema)
            table = self.client.create_table(table)
            print(f"✓ Created NetSuite events table {self.events_table}")
    
    def log_event(self, 
                  direction: str,
                  event_type: str,
                  event_category: str,
                  status: str,
                  entity_type: str = None,
                  entity_id: str = None,
                  netsuite_id: str = None,
                  action: str = None,
                  request_data: Dict = None,
                  response_data: Dict = None,
                  error_message: str = None,
                  duration_ms: int = None,
                  user: str = None,
                  metadata: Dict = None) -> bool:
        """Log a NetSuite sync event"""
        try:
            from uuid import uuid4
            
            event = {
                "event_id": str(uuid4()),
                "timestamp": datetime.utcnow().isoformat(),
                "direction": direction,  # OUTBOUND or INBOUND
                "event_type": event_type,
                "event_category": event_category,
                "status": status,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "netsuite_id": netsuite_id,
                "action": action,
                "request_data": json.dumps(request_data) if request_data else None,
                "response_data": json.dumps(response_data) if response_data else None,
                "error_message": error_message,
                "duration_ms": duration_ms,
                "user": user or "SYSTEM",
                "metadata": json.dumps(metadata) if metadata else None
            }
            
            table = self.client.get_table(self.events_table)
            errors = self.client.insert_rows_json(table, [event])
            
            if errors:
                print(f"❌ Failed to log event: {errors}")
                return False
            
            return True
            
        except Exception as e:
            print(f"Error logging NetSuite event: {e}")
            traceback.print_exc()
            return False
    
    def get_events(self, 
                   direction: str = None,
                   event_category: str = None,
                   entity_id: str = None,
                   netsuite_id: str = None,
                   status: str = None,
                   hours: int = 24,
                   limit: int = 100) -> List[Dict]:
        """Get NetSuite events with filters"""
        try:
            # Build query
            where_clauses = [f"timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)"]
            
            if direction:
                where_clauses.append(f"direction = '{direction}'")
            if event_category:
                where_clauses.append(f"event_category = '{event_category}'")
            if entity_id:
                where_clauses.append(f"entity_id = '{entity_id}'")
            if netsuite_id:
                where_clauses.append(f"netsuite_id = '{netsuite_id}'")
            if status:
                where_clauses.append(f"status = '{status}'")
            
            where_clause = " AND ".join(where_clauses)
            
            query = f"""
            SELECT *
            FROM `{self.events_table}`
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT {limit}
            """
            
            results = self.client.query(query).result()
            
            events = []
            for row in results:
                event = {
                    'event_id': row.event_id,
                    'timestamp': row.timestamp.isoformat() if row.timestamp else None,
                    'direction': row.direction,
                    'event_type': row.event_type,
                    'event_category': row.event_category,
                    'status': row.status,
                    'entity_type': row.entity_type,
                    'entity_id': row.entity_id,
                    'netsuite_id': row.netsuite_id,
                    'action': row.action,
                    'request_data': json.loads(row.request_data) if row.request_data else None,
                    'response_data': json.loads(row.response_data) if row.response_data else None,
                    'error_message': row.error_message,
                    'duration_ms': row.duration_ms,
                    'user': row.user,
                    'metadata': json.loads(row.metadata) if row.metadata else None
                }
                events.append(event)
            
            return events
            
        except Exception as e:
            print(f"Error getting NetSuite events: {e}")
            traceback.print_exc()
            return []
    
    def get_event_statistics(self) -> Dict:
        """Get statistics about NetSuite events"""
        try:
            query = f"""
            WITH stats AS (
                SELECT 
                    COUNT(*) as total_events,
                    COUNTIF(direction = 'OUTBOUND') as outbound_count,
                    COUNTIF(direction = 'INBOUND') as inbound_count,
                    COUNTIF(status = 'SUCCESS') as success_count,
                    COUNTIF(status = 'FAILED') as failed_count,
                    COUNTIF(status = 'PENDING') as pending_count,
                    AVG(CASE WHEN duration_ms IS NOT NULL THEN duration_ms END) as avg_duration_ms,
                    MAX(timestamp) as last_event_time
                FROM `{self.events_table}`
                WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            ),
            category_stats AS (
                SELECT 
                    event_category,
                    COUNT(*) as count,
                    COUNTIF(status = 'SUCCESS') as success,
                    COUNTIF(status = 'FAILED') as failed
                FROM `{self.events_table}`
                WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
                GROUP BY event_category
            ),
            recent_failures AS (
                SELECT 
                    event_type,
                    error_message,
                    timestamp
                FROM `{self.events_table}`
                WHERE status = 'FAILED'
                    AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
                ORDER BY timestamp DESC
                LIMIT 5
            )
            SELECT 
                (SELECT TO_JSON_STRING(stats) FROM stats) as overall_stats,
                ARRAY_AGG(STRUCT(
                    category_stats.event_category,
                    category_stats.count,
                    category_stats.success,
                    category_stats.failed
                )) as category_breakdown,
                ARRAY_AGG(STRUCT(
                    recent_failures.event_type,
                    recent_failures.error_message,
                    recent_failures.timestamp
                )) as recent_failures
            FROM stats, category_stats, recent_failures
            """
            
            results = self.client.query(query).result()
            
            for row in results:
                stats = json.loads(row.overall_stats) if row.overall_stats else {}
                return {
                    'total_events': stats.get('total_events', 0),
                    'outbound_count': stats.get('outbound_count', 0),
                    'inbound_count': stats.get('inbound_count', 0),
                    'success_count': stats.get('success_count', 0),
                    'failed_count': stats.get('failed_count', 0),
                    'pending_count': stats.get('pending_count', 0),
                    'avg_duration_ms': round(stats.get('avg_duration_ms', 0)) if stats.get('avg_duration_ms') else 0,
                    'last_event_time': stats.get('last_event_time'),
                    'category_breakdown': row.category_breakdown if row.category_breakdown else [],
                    'recent_failures': row.recent_failures if row.recent_failures else []
                }
            
            return {
                'total_events': 0,
                'outbound_count': 0,
                'inbound_count': 0,
                'success_count': 0,
                'failed_count': 0,
                'pending_count': 0,
                'avg_duration_ms': 0,
                'category_breakdown': []
            }
            
        except Exception as e:
            print(f"Error getting event statistics: {e}")
            traceback.print_exc()
            return {}
    
    def get_supported_events(self) -> Dict:
        """Get list of all supported event types"""
        return {
            'outbound': {
                'vendor': [
                    {'type': 'vendor_create', 'description': 'Create new vendor in NetSuite'},
                    {'type': 'vendor_update', 'description': 'Update existing vendor in NetSuite'},
                    {'type': 'vendor_sync', 'description': 'Sync vendor data to NetSuite'},
                    {'type': 'vendor_validate', 'description': 'Validate vendor in NetSuite'},
                ],
                'invoice': [
                    {'type': 'invoice_create', 'description': 'Create vendor bill from invoice'},
                    {'type': 'invoice_update', 'description': 'Update existing vendor bill'},
                    {'type': 'invoice_sync', 'description': 'Sync invoice to NetSuite'},
                ],
                'payment': [
                    {'type': 'payment_create', 'description': 'Create bill payment in NetSuite'},
                    {'type': 'payment_apply', 'description': 'Apply payment to vendor bill'},
                ],
                'query': [
                    {'type': 'metadata_fetch', 'description': 'Fetch NetSuite metadata catalog'},
                    {'type': 'vendor_search', 'description': 'Search vendors in NetSuite'},
                    {'type': 'bill_status', 'description': 'Check bill status in NetSuite'},
                ]
            },
            'inbound': {
                'vendor': [
                    {'type': 'vendor_import', 'description': 'Import vendors from NetSuite'},
                    {'type': 'vendor_webhook', 'description': 'Vendor update webhook from NetSuite'},
                ],
                'bill': [
                    {'type': 'bill_approved', 'description': 'Bill approved in NetSuite'},
                    {'type': 'bill_rejected', 'description': 'Bill rejected in NetSuite'},
                    {'type': 'bill_paid', 'description': 'Bill payment received'},
                    {'type': 'bill_status_change', 'description': 'Bill status changed'},
                ],
                'payment': [
                    {'type': 'payment_received', 'description': 'Payment received notification'},
                    {'type': 'payment_reversed', 'description': 'Payment reversal notification'},
                ],
                'sync': [
                    {'type': 'bulk_sync', 'description': 'Bulk data sync from NetSuite'},
                    {'type': 'scheduled_pull', 'description': 'Scheduled data pull from NetSuite'},
                ]
            }
        }