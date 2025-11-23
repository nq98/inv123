import json
from google.genai import types


class VendorMatcher:
    """
    3-Step Vendor Matching Engine with Supreme Judge Semantic Reasoning
    
    Pipeline:
        Step 0: Hard Match (Fast SQL) - Tax ID exact match in BigQuery → 100% confidence
        Step 1: Semantic Retrieval (Vertex AI Search RAG) - Find Top 5 similar vendors
        Step 2: The Supreme Judge (Gemini 1.5 Pro) - Semantic reasoning: MATCH | NEW_VENDOR | AMBIGUOUS
    """
    
    def __init__(self, bigquery_service, vertex_search_service, gemini_service):
        """
        Initialize VendorMatcher with required services
        
        Args:
            bigquery_service: BigQueryService instance for database operations
            vertex_search_service: VertexSearchService instance for semantic search
            gemini_service: GeminiService instance for Supreme Judge reasoning
        """
        self.bigquery = bigquery_service
        self.vertex_search = vertex_search_service
        self.gemini = gemini_service
    
    def match_vendor(self, invoice_data, classifier_verdict=None):
        """
        3-step vendor matching pipeline with optional AI-first entity classification
        
        Args:
            invoice_data: dict with vendor_name, tax_id, address, email_domain, phone, country
                Example: {
                    "vendor_name": "Amazon AWS",
                    "tax_id": "US123456789",
                    "address": "410 Terry Ave N, Seattle, WA",
                    "email_domain": "@aws.com",
                    "phone": "+1-206-555-0100",
                    "country": "US"
                }
            classifier_verdict: Optional dict with semantic entity classification result
                Example: {
                    "entity_type": "BANK",
                    "confidence": "HIGH",
                    "reasoning": "This is a financial institution",
                    "is_valid_vendor": False
                }
        
        Returns:
            dict: {
                "verdict": "MATCH" | "NEW_VENDOR" | "AMBIGUOUS" | "INVALID_VENDOR",
                "vendor_id": str or None,
                "confidence": float (0.0-1.0),
                "reasoning": str,
                "risk_analysis": str,
                "database_updates": {
                    "add_new_alias": str or None,
                    "add_new_address": str or None,
                    "add_new_domain": str or None
                },
                "parent_child_logic": {
                    "is_subsidiary": bool,
                    "parent_company_detected": str or None
                },
                "method": str (TAX_ID_HARD_MATCH, SEMANTIC_MATCH, NEW_VENDOR, or semantic_classifier_rejection)
            }
        """
        vendor_name = invoice_data.get('vendor_name', 'Unknown')
        print(f"🔍 Starting vendor matching for: {vendor_name}")
        
        # CRITICAL FIX 3: If classifier already rejected entity, don't even try matching
        if classifier_verdict and not classifier_verdict.get('is_valid_vendor', True):
            entity_type = classifier_verdict.get('entity_type', 'UNKNOWN')
            reasoning = classifier_verdict.get('reasoning', 'Entity classified as non-vendor')
            confidence_str = classifier_verdict.get('confidence', 'HIGH')
            
            # Map confidence string to float
            confidence_map = {'HIGH': 0.95, 'MEDIUM': 0.75, 'LOW': 0.5}
            confidence_score = confidence_map.get(confidence_str, 0.95)
            
            print(f"❌ REJECTED by semantic classifier: {vendor_name} is {entity_type}")
            print(f"   Reasoning: {reasoning}")
            
            return {
                'verdict': 'INVALID_VENDOR',
                'entity_type': entity_type,
                'vendor_id': None,
                'confidence': confidence_score,
                'reasoning': f"Semantic classifier rejected: {reasoning}",
                'risk_analysis': 'HIGH',
                'database_updates': {},
                'parent_child_logic': {
                    'is_subsidiary': False,
                    'parent_company_detected': None
                },
                'method': 'semantic_classifier_rejection'
            }
        
        # STEP 0: Hard Match by Tax ID (100% confidence if found)
        tax_id = invoice_data.get('tax_id', '')
        if tax_id and tax_id != 'Unknown':
            print(f"⚡ Step 0: Checking hard Tax ID match for {tax_id}...")
            hard_match = self._hard_match_by_tax_id(tax_id)
            
            if hard_match:
                print(f"✅ Hard match found: {hard_match['vendor_id']} (confidence: 1.0)")
                return {
                    "verdict": "MATCH",
                    "vendor_id": hard_match['vendor_id'],
                    "confidence": 1.0,
                    "reasoning": f"Exact Tax ID match: {tax_id}",
                    "risk_analysis": "NONE",
                    "database_updates": {},
                    "parent_child_logic": {
                        "is_subsidiary": False,
                        "parent_company_detected": None
                    },
                    "method": "TAX_ID_HARD_MATCH"
                }
        
        # STEP 1: Semantic Candidate Retrieval (Vertex AI Search RAG)
        vendor_name = invoice_data.get('vendor_name', '')
        country = invoice_data.get('country')
        
        if not vendor_name or vendor_name == 'Unknown':
            print("⚠️ No vendor name provided, cannot perform semantic matching")
            return {
                "verdict": "NEW_VENDOR",
                "vendor_id": None,
                "confidence": 0.0,
                "reasoning": "No vendor name provided for matching",
                "risk_analysis": "HIGH",
                "database_updates": {},
                "parent_child_logic": {
                    "is_subsidiary": False,
                    "parent_company_detected": None
                },
                "method": "NEW_VENDOR"
            }
        
        print(f"🔎 Step 1: Semantic search for '{vendor_name}' (country: {country})...")
        candidates = self._get_semantic_candidates(vendor_name, country, top_k=5)
        
        if not candidates:
            print("⚠️ No semantic candidates found, likely a NEW_VENDOR")
            return {
                "verdict": "NEW_VENDOR",
                "vendor_id": None,
                "confidence": 0.0,
                "reasoning": f"No similar vendors found in database for '{vendor_name}'",
                "risk_analysis": "LOW",
                "database_updates": {},
                "parent_child_logic": {
                    "is_subsidiary": False,
                    "parent_company_detected": None
                },
                "method": "NEW_VENDOR"
            }
        
        print(f"📋 Found {len(candidates)} semantic candidates")
        
        # STEP 2: Supreme Judge Decision (Gemini 1.5 Pro)
        print(f"⚖️ Step 2: Invoking Supreme Judge (Gemini 1.5 Pro)...")
        judge_decision = self._supreme_judge_decision(invoice_data, candidates, classifier_verdict)
        
        # Apply self-healing database updates if verdict is MATCH
        if judge_decision['verdict'] == 'MATCH' and judge_decision['vendor_id']:
            updates = judge_decision.get('database_updates', {})
            if any(updates.values()):
                print(f"🔧 Applying self-healing updates to vendor {judge_decision['vendor_id']}...")
                self._apply_database_updates(judge_decision['vendor_id'], updates)
        
        # Add method to result (must be one of: TAX_ID_HARD_MATCH, SEMANTIC_MATCH, NEW_VENDOR)
        if judge_decision['verdict'] == 'MATCH':
            judge_decision['method'] = 'SEMANTIC_MATCH'
        elif judge_decision['verdict'] == 'NEW_VENDOR':
            judge_decision['method'] = 'NEW_VENDOR'
        else:  # AMBIGUOUS or other
            judge_decision['method'] = 'SEMANTIC_MATCH'  # Went through semantic process
        
        print(f"📊 Final verdict: {judge_decision['verdict']} (confidence: {judge_decision['confidence']:.2f})")
        return judge_decision
    
    def _hard_match_by_tax_id(self, tax_id):
        """
        Step 0: Query BigQuery for exact Tax ID match
        Supports: VAT, EIN, GST, HP, CNPJ, etc.
        
        Args:
            tax_id: Tax registration ID to search for
            
        Returns:
            dict with vendor_id and vendor_name if found, None otherwise
        """
        if not tax_id or tax_id == "Unknown":
            return None
        
        # Clean tax ID (remove spaces, dashes, common prefixes)
        clean_tax_id = tax_id.replace(" ", "").replace("-", "").upper()
        
        # BigQuery query to search in custom_attributes JSON field
        query = f"""
        SELECT 
            vendor_id,
            global_name,
            normalized_name,
            emails,
            domains,
            countries,
            custom_attributes
        FROM `{self.bigquery.full_table_id}`
        WHERE 
            JSON_VALUE(custom_attributes, '$.tax_id') IS NOT NULL
            AND REPLACE(REPLACE(UPPER(JSON_VALUE(custom_attributes, '$.tax_id')), ' ', ''), '-', '') = @clean_tax_id
        LIMIT 1
        """
        
        try:
            from google.cloud import bigquery
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("clean_tax_id", "STRING", clean_tax_id)
                ]
            )
            
            results = list(self.bigquery.client.query(query, job_config=job_config).result())
            
            if results:
                row = results[0]
                return {
                    "vendor_id": row.vendor_id,
                    "vendor_name": row.global_name,
                    "confidence": 1.0,
                    "method": "TAX_ID_HARD_MATCH"
                }
            
            return None
            
        except Exception as e:
            print(f"❌ Tax ID query error: {e}")
            return None
    
    def _get_semantic_candidates(self, vendor_name, country=None, top_k=5):
        """
        Step 1: Use Vertex AI Search to find semantically similar vendors
        
        Args:
            vendor_name: Vendor name to search for
            country: Optional country filter
            top_k: Maximum number of candidates to return
            
        Returns:
            List of candidate vendor dicts with metadata
        """
        if not vendor_name or vendor_name == "Unknown":
            return []
        
        # Build search query
        search_query = f"Find vendor: {vendor_name}"
        if country:
            search_query += f" in {country}"
        
        try:
            # Use Vertex Search service (search_vendor method)
            search_results = self.vertex_search.search_vendor(
                vendor_query=search_query,
                max_results=top_k
            )
            
            # CRITICAL FIX: Check if Vertex returned empty results
            # (could be no matches OR error was caught internally)
            if not search_results or len(search_results) == 0:
                print(f"⚠️ Vertex Search returned no results (may have failed silently)")
                print(f"🔄 Triggering BigQuery fallback for '{vendor_name}'...")
                
                # Call BigQuery fallback
                bigquery_results = self.bigquery.search_vendor_by_name(
                    vendor_name=vendor_name,
                    limit=top_k
                )
                
                if not bigquery_results:
                    print(f"⚠️ BigQuery fallback also returned no results")
                    return []
                
                print(f"✅ BigQuery fallback found {len(bigquery_results)} candidates")
                
                # Convert BigQuery results to Vertex Search format
                candidates = []
                for vendor in bigquery_results:
                    custom_attrs = vendor.get('custom_attributes', {})
                    if isinstance(custom_attrs, str):
                        try:
                            custom_attrs = json.loads(custom_attrs)
                        except:
                            custom_attrs = {}
                    
                    tax_ids = [custom_attrs.get('tax_id')] if custom_attrs.get('tax_id') else []
                    addresses = [custom_attrs.get('address')] if custom_attrs.get('address') else []
                    
                    candidates.append({
                        "candidate_id": vendor.get('vendor_id'),
                        "global_name": vendor.get('global_name', 'Unknown'),
                        "normalized_name": vendor.get('normalized_name', ''),
                        "aliases": [vendor.get('normalized_name')] if vendor.get('normalized_name') else [],
                        "tax_ids": tax_ids,
                        "domains": vendor.get('domains', []),
                        "emails": vendor.get('emails', []),
                        "addresses": addresses,
                        "countries": vendor.get('countries', []),
                        "custom_attributes": custom_attrs
                    })
                
                return candidates
            
            # Vertex Search returned results, format them normally
            candidates = []
            
            for result in search_results:
                data = result.get('data', {})
                
                # Extract vendor information
                vendor_id = data.get('vendor_id', 'unknown')
                global_name = data.get('global_name', data.get('vendor_name', 'Unknown'))
                normalized_name = data.get('normalized_name', '')
                
                # Extract arrays
                emails = data.get('emails', [])
                domains = data.get('domains', [])
                countries_list = data.get('countries', [])
                
                # Extract custom attributes
                custom_attrs = data.get('custom_attributes', {})
                if isinstance(custom_attrs, str):
                    try:
                        custom_attrs = json.loads(custom_attrs)
                    except:
                        custom_attrs = {}
                
                # Extract tax IDs from custom attributes
                tax_ids = []
                if custom_attrs.get('tax_id'):
                    tax_ids.append(custom_attrs['tax_id'])
                
                # Extract addresses from custom attributes
                addresses = []
                if custom_attrs.get('address'):
                    addresses.append(custom_attrs['address'])
                
                candidates.append({
                    "candidate_id": vendor_id,
                    "global_name": global_name,
                    "normalized_name": normalized_name,
                    "aliases": [normalized_name] if normalized_name else [],
                    "tax_ids": tax_ids,
                    "domains": domains if isinstance(domains, list) else [],
                    "emails": emails if isinstance(emails, list) else [],
                    "addresses": addresses,
                    "countries": countries_list if isinstance(countries_list, list) else [],
                    "custom_attributes": custom_attrs
                })
            
            return candidates
            
        except Exception as e:
            print(f"❌ Semantic search error: {e}")
            print(f"🔄 Falling back to BigQuery direct search...")
            
            # FALLBACK: Search BigQuery directly using LIKE pattern matching
            try:
                bigquery_results = self.bigquery.search_vendor_by_name(
                    vendor_name=vendor_name,
                    limit=top_k
                )
                
                if not bigquery_results:
                    print(f"⚠️ BigQuery fallback also returned no results for '{vendor_name}'")
                    return []
                
                print(f"✅ BigQuery fallback found {len(bigquery_results)} candidates")
                
                # Convert BigQuery results to same format as Vertex Search results
                candidates = []
                for vendor in bigquery_results:
                    # Extract custom attributes
                    custom_attrs = vendor.get('custom_attributes', {})
                    if isinstance(custom_attrs, str):
                        try:
                            custom_attrs = json.loads(custom_attrs)
                        except:
                            custom_attrs = {}
                    
                    # Extract tax IDs from custom attributes
                    tax_ids = []
                    if custom_attrs.get('tax_id'):
                        tax_ids.append(custom_attrs['tax_id'])
                    
                    # Extract addresses from custom attributes  
                    addresses = []
                    if custom_attrs.get('address'):
                        addresses.append(custom_attrs['address'])
                    
                    candidates.append({
                        "candidate_id": vendor.get('vendor_id'),
                        "global_name": vendor.get('global_name', 'Unknown'),
                        "normalized_name": vendor.get('normalized_name', ''),
                        "aliases": [vendor.get('normalized_name', '')] if vendor.get('normalized_name') else [],
                        "tax_ids": tax_ids,
                        "domains": vendor.get('domains', []),
                        "emails": vendor.get('emails', []),
                        "addresses": addresses,
                        "countries": vendor.get('countries', []),
                        "custom_attributes": custom_attrs
                    })
                
                return candidates
                
            except Exception as bigquery_error:
                print(f"❌ BigQuery fallback also failed: {bigquery_error}")
                return []
    
    def _supreme_judge_decision(self, invoice_data, candidates, classifier_verdict=None):
        """
        Step 2: Gemini 1.5 Pro acts as Supreme Judge
        
        Uses comprehensive semantic reasoning to decide:
        - MATCH: Invoice vendor matches existing database vendor
        - NEW_VENDOR: No match found, this is a new vendor
        - AMBIGUOUS: Uncertain, requires human review
        - INVALID_VENDOR: Entity is not a valid vendor (bank, payment processor, etc.)
        
        Args:
            invoice_data: Invoice vendor information
            candidates: List of semantic candidate vendors from Vertex Search
            classifier_verdict: Optional pre-classification from semantic entity classifier
            
        Returns:
            dict with verdict, vendor_id, confidence, reasoning, database_updates
        """
        # Extract invoice vendor details
        vendor_name = invoice_data.get("vendor_name", "Unknown")
        tax_id = invoice_data.get("tax_id", "")
        address = invoice_data.get("address", "")
        email_domain = invoice_data.get("email_domain", "")
        phone = invoice_data.get("phone", "")
        bank_tail = invoice_data.get("bank_account_last4", "")
        country = invoice_data.get("country", "")
        
        # Format candidates for prompt
        candidates_json = json.dumps(candidates, indent=2)
        
        # Build entity classification section if classifier verdict provided
        entity_classification_section = ""
        if classifier_verdict:
            entity_type = classifier_verdict.get('entity_type', 'VENDOR')
            confidence = classifier_verdict.get('confidence', 'UNKNOWN')
            reasoning = classifier_verdict.get('reasoning', 'No reasoning provided')
            
            entity_classification_section = f"""
### 🤖 ENTITY CLASSIFICATION (Pre-validated by AI Classifier)
The entity "{vendor_name}" has been pre-classified as: **{entity_type}**
Classifier confidence: {confidence}
Classifier reasoning: {reasoning}

**CRITICAL:** You MUST honor this classification. If the classifier determined this is NOT a vendor 
(BANK, PAYMENT_PROCESSOR, GOVERNMENT_ENTITY, INDIVIDUAL_PERSON), you MUST return verdict="INVALID_VENDOR".
"""
        
        # Supreme Court Judge Prompt
        prompt = f"""
You are the **Supreme Data Judge**. You preside over the Vendor Master Database.
Your job is to decide, beyond a reasonable doubt, if the **INVOICE VENDOR** matches one of the **DATABASE CANDIDATES**.

### THE EVIDENCE
**1. THE INVOICE VENDOR (The Newcomer):**
- **Raw Name:** "{vendor_name}"
- **Extracted Tax ID:** "{tax_id}" (VAT/EIN/GST/HP/CNPJ)
- **Extracted Address:** "{address}"
- **Sender Domain:** "{email_domain}" (e.g., @uber.com)
- **Phone:** "{phone}"
- **Bank Account Last 4:** "{bank_tail}"
- **Country:** "{country}"

**2. THE DATABASE CANDIDATES (The Existing Records):**
{candidates_json}
{entity_classification_section}

### 🔍 ENTITY VALIDATION (CRITICAL FIRST STEP)
Before making your decision, verify that the invoice vendor is a legitimate business vendor:
- **NOT a bank** (e.g., "Chase Bank", "JPMorgan Chase Bank, N.A.", "Wells Fargo", "HSBC", "Barclays")
- **NOT a payment processor** (e.g., "PayPal", "Stripe", "Square", "Venmo", "Wise")
- **NOT a government entity** (e.g., "IRS", "Tax Authority", "HMRC", "Treasury Department")

**If the vendor is INVALID (bank/payment processor/government), return:**
{{
    "verdict": "INVALID_VENDOR",
    "match_details": {{
        "selected_vendor_id": null,
        "confidence_score": 1.0,
        "match_reasoning": "Entity classified as [BANK|PAYMENT_PROCESSOR|GOVERNMENT_ENTITY], not a valid vendor",
        "risk_analysis": "HIGH",
        "entity_type": "BANK" | "PAYMENT_PROCESSOR" | "GOVERNMENT_ENTITY"
    }},
    "database_updates": {{}},
    "parent_child_logic": {{
        "is_subsidiary": false,
        "parent_company_detected": null
    }}
}}

### ⚖️ JUDICIAL LOGIC (THE LAWS OF MATCHING)

**LAW 1: THE HIERARCHY OF IDENTIFIERS (Hard Evidence)**
- **Tax ID Match:** If Tax IDs match exactly, VERDICT = **MATCH** (Confidence 1.0). Ignore name spelling differences.
- **Bank Account Match:** If IBAN/Account Number matches known history, VERDICT = **MATCH**.
- **Domain Match:** 
    - If domain is Corporate (e.g., `@google.com`), and names are similar, VERDICT = **MATCH**.
    - **WARNING:** If domain is Generic (`@gmail.com`, `@yahoo.co.uk`), IGNORE IT. You must rely on Name + Address.

**LAW 2: SEMANTIC FLEXIBILITY (Soft Evidence)**
- **Fuzzy Names:** "Amazon Web Srvcs" == "Amazon AWS" == "Amazon.com Inc."
- **Acquisitions:** If Invoice says "Slack" but DB candidate is "Salesforce", and address matches Salesforce, VERDICT = **MATCH** (Parent/Child).
- **Multilingual:** "חברת חשמל" (Hebrew) == "Israel Electric Corp" (English).
- **Typo Tolerance:** "Microsft" == "Microsoft".

**LAW 3: THE "FALSE FRIEND" TRAP (Do Not Hallucinate)**
- **Same Name, Different Entity:** "Apple Landscaping" != "Apple Inc." (Check Industry/Address).
- **Franchises:** "McDonalds (Tel Aviv Branch)" vs "McDonalds (HQ US)". 
    - If we pay the HQ, match to HQ.
    - If we pay the branch directly, match to HQ *unless* DB has specific branch IDs.

**LAW 4: DATA EVOLUTION (Self-Healing)**
- If the Vendor is a MATCH, but the Address on the invoice is different from the DB, flag it as a **"New Address Discovery"**.
- If the Vendor uses a new Alias (e.g., DB has "Facebook", Invoice says "Meta"), flag it as a **"New Alias Discovery"**.
- If the Vendor uses a new Domain (e.g., DB has "@fb.com", Invoice says "@meta.com"), flag it as a **"New Domain Discovery"**.

### 📝 THE VERDICT SCHEMA (JSON ONLY)
{{
    "verdict": "MATCH" | "NEW_VENDOR" | "AMBIGUOUS",
    "match_details": {{
        "selected_vendor_id": "string (ID from DB Candidate) or null",
        "confidence_score": 0.0-1.0,
        "match_reasoning": "Explain specifically: 'Matched via Tax ID', 'Matched via Corporate Domain + Fuzzy Name', etc.",
        "risk_analysis": "NONE | LOW | HIGH (e.g. 'Name matches but domain is gmail.com')"
    }},
    "database_updates": {{
        "add_new_alias": "string (If invoice name is a valid nickname not in DB) or null",
        "add_new_address": "string (If matched, but address is new) or null",
        "add_new_domain": "string (If matched, but domain is new) or null"
    }},
    "parent_child_logic": {{
        "is_subsidiary": true|false,
        "parent_company_detected": "string or null"
    }}
}}

**IMPORTANT RULES:**
1. If NO candidates are provided or all candidates have very low similarity, VERDICT = **NEW_VENDOR**
2. If multiple candidates are equally plausible, VERDICT = **AMBIGUOUS**
3. If you are 70%+ confident of a match, VERDICT = **MATCH**
4. ALWAYS provide detailed match_reasoning explaining your decision
5. Return ONLY valid JSON, no markdown, no commentary
"""
        
        try:
            # Call Gemini 1.5 Pro with automatic fallback (rate limit protection)
            response = self.gemini._generate_content_with_fallback(
                model='gemini-1.5-pro',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type='application/json'
                )
            )
            
            # Parse JSON response
            result = json.loads(response.text or "{}")
            
            # Get verdict and normalize if needed (AMBIGUOUS → NEW_VENDOR for method mapping)
            raw_verdict = result.get("verdict", "NEW_VENDOR")
            # Ensure verdict is one of the three allowed values
            if raw_verdict not in ["MATCH", "NEW_VENDOR", "AMBIGUOUS"]:
                raw_verdict = "NEW_VENDOR"
            
            return {
                "verdict": raw_verdict,
                "vendor_id": result.get("match_details", {}).get("selected_vendor_id"),
                "confidence": result.get("match_details", {}).get("confidence_score", 0.0),
                "reasoning": result.get("match_details", {}).get("match_reasoning", "No reasoning provided"),
                "risk_analysis": result.get("match_details", {}).get("risk_analysis", "UNKNOWN"),
                "database_updates": result.get("database_updates", {}),
                "parent_child_logic": result.get("parent_child_logic", {
                    "is_subsidiary": False,
                    "parent_company_detected": None
                })
            }
            
        except Exception as e:
            print(f"❌ Supreme Judge error: {e}")
            # On error, return NEW_VENDOR (safer than AMBIGUOUS for method mapping)
            return {
                "verdict": "NEW_VENDOR",
                "vendor_id": None,
                "confidence": 0.0,
                "reasoning": f"Error during Supreme Judge decision: {str(e)}",
                "risk_analysis": "HIGH",
                "database_updates": {},
                "parent_child_logic": {
                    "is_subsidiary": False,
                    "parent_company_detected": None
                }
            }
    
    def _apply_database_updates(self, vendor_id, updates):
        """
        Apply self-healing updates to BigQuery vendor database
        
        Automatically adds:
        - New aliases (vendor name variations)
        - New addresses (additional vendor locations)
        - New domains (new email domains used by vendor)
        
        Args:
            vendor_id: Vendor ID to update
            updates: dict with add_new_alias, add_new_address, add_new_domain
        """
        if not vendor_id or not updates:
            return
        
        try:
            # Build update for custom_attributes JSON field
            update_parts = []
            
            # Get current vendor data
            query = f"""
            SELECT custom_attributes
            FROM `{self.bigquery.full_table_id}`
            WHERE vendor_id = @vendor_id
            LIMIT 1
            """
            
            from google.cloud import bigquery
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("vendor_id", "STRING", vendor_id)
                ]
            )
            
            results = list(self.bigquery.client.query(query, job_config=job_config).result())
            
            if not results:
                print(f"⚠️ Vendor {vendor_id} not found for update")
                return
            
            # Parse current custom_attributes
            current_attrs = results[0].custom_attributes
            if isinstance(current_attrs, str):
                current_attrs = json.loads(current_attrs)
            elif not isinstance(current_attrs, dict):
                current_attrs = {}
            
            # Update custom_attributes with new data
            if updates.get("add_new_alias"):
                aliases = current_attrs.get("aliases", [])
                if updates["add_new_alias"] not in aliases:
                    aliases.append(updates["add_new_alias"])
                    current_attrs["aliases"] = aliases
                    update_parts.append(f"alias: {updates['add_new_alias']}")
            
            if updates.get("add_new_address"):
                addresses = current_attrs.get("addresses", [])
                if updates["add_new_address"] not in addresses:
                    addresses.append(updates["add_new_address"])
                    current_attrs["addresses"] = addresses
                    update_parts.append(f"address: {updates['add_new_address']}")
            
            if updates.get("add_new_domain"):
                # Update domains array (not in custom_attributes)
                domain = updates["add_new_domain"].strip('@')
                update_domain_query = f"""
                UPDATE `{self.bigquery.full_table_id}`
                SET domains = ARRAY_CONCAT(
                    IFNULL(domains, []),
                    [@domain]
                )
                WHERE vendor_id = @vendor_id
                AND NOT @domain IN UNNEST(IFNULL(domains, []))
                """
                
                domain_job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("vendor_id", "STRING", vendor_id),
                        bigquery.ScalarQueryParameter("domain", "STRING", domain)
                    ]
                )
                
                self.bigquery.client.query(update_domain_query, job_config=domain_job_config).result()
                update_parts.append(f"domain: {domain}")
            
            # Update custom_attributes JSON
            if current_attrs:
                update_query = f"""
                UPDATE `{self.bigquery.full_table_id}`
                SET 
                    custom_attributes = @custom_attrs,
                    last_updated = CURRENT_TIMESTAMP()
                WHERE vendor_id = @vendor_id
                """
                
                update_job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("vendor_id", "STRING", vendor_id),
                        bigquery.ScalarQueryParameter("custom_attrs", "JSON", json.dumps(current_attrs))
                    ]
                )
                
                self.bigquery.client.query(update_query, job_config=update_job_config).result()
            
            if update_parts:
                print(f"✅ Self-healing update applied to vendor {vendor_id}: {', '.join(update_parts)}")
            
        except Exception as e:
            print(f"❌ Database update error: {e}")
