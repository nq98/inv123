class AgentSearchService:
    def __init__(self, vertex_search_service, bigquery_service):
        self.vertex = vertex_search_service
        self.bq = bigquery_service
    
    def search(self, query, client_id, filters=None, max_results=50):
        """
        Unified search with full metadata as per contract
        Returns: List of search results with type indicators and full metadata
        """
        results = []
        
        try:
            vendor_results = self.vertex.search_vendor_by_name(query, top_k=max_results//2)
            for v in vendor_results:
                results.append({
                    'type': 'vendor',
                    'vendor_id': v.get('vendor_id'),
                    'vendor_name': v.get('name', v.get('global_name', 'Unknown')),
                    'vendor_email': v.get('email', v.get('emails', [None])[0] if v.get('emails') else None),
                    'score': v.get('score', 0.0),
                    'source': 'vertex_search',
                    'metadata': v
                })
        except Exception as e:
            print(f"Warning: Vertex search failed: {e}")
            try:
                bq_vendor_query = """
                SELECT vendor_id, global_name, emails, domains, countries, custom_attributes
                FROM vendors_ai.global_vendors
                WHERE LOWER(global_name) LIKE @search
                LIMIT @limit
                """
                vendor_fallback = self.bq.query(bq_vendor_query, {
                    'search': f'%{query.lower()}%',
                    'limit': max_results//2
                })
                
                for v in vendor_fallback:
                    results.append({
                        'type': 'vendor',
                        'vendor_id': v.get('vendor_id'),
                        'vendor_name': v.get('global_name', 'Unknown'),
                        'vendor_email': v.get('emails', [None])[0] if v.get('emails') else None,
                        'score': 0.5,
                        'source': 'bigquery_fallback',
                        'metadata': dict(v)
                    })
            except Exception as e2:
                print(f"Warning: BigQuery vendor fallback also failed: {e2}")
        
        invoice_query = """
        SELECT invoice_id, vendor_name, vendor_id, amount, currency, invoice_date, client_id, status, metadata
        FROM vendors_ai.invoices
        WHERE client_id = @client_id
        AND (LOWER(vendor_name) LIKE @search OR invoice_id LIKE @search)
        ORDER BY invoice_date DESC
        LIMIT @limit
        """
        
        try:
            invoice_results = self.bq.query(invoice_query, {
                'client_id': client_id,
                'search': f'%{query.lower()}%',
                'limit': max_results//2
            })
            
            for inv in invoice_results:
                results.append({
                    'type': 'invoice',
                    'invoice_id': inv.get('invoice_id'),
                    'vendor_id': inv.get('vendor_id'),
                    'vendor_name': inv.get('vendor_name'),
                    'amount': float(inv.get('amount', 0)),
                    'currency': inv.get('currency', 'USD'),
                    'invoice_date': str(inv.get('invoice_date')) if inv.get('invoice_date') else None,
                    'status': inv.get('status', 'unknown'),
                    'source': 'bigquery',
                    'metadata': dict(inv)
                })
        except Exception as e:
            print(f"Warning: Invoice search failed: {e}")
        
        return results[:max_results]
