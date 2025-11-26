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
        
        # STEP 1: Semantic Candidate Retrieval (Vertex AI Search RAG + alternative signals)
        vendor_name = invoice_data.get('vendor_name', '')
        resolved_legal_name = invoice_data.get('resolved_legal_name', '')
        country = invoice_data.get('country')
        tax_id = invoice_data.get('tax_id', '')
        email_domain = invoice_data.get('email_domain', '')
        iban = invoice_data.get('iban', '')
        
        # BUG FIX #2: Don't abort if name is missing - check other identity signals
        candidates = []
        
        # Try vendor name search first (if available) - DUAL-NAME SEARCH
        if vendor_name and vendor_name != 'Unknown':
            print(f"🔎 Step 1: Semantic search for '{vendor_name}' (country: {country})...")
            if resolved_legal_name and resolved_legal_name != 'Unknown' and resolved_legal_name != vendor_name:
                print(f"   📝 Also have resolved legal name: '{resolved_legal_name}'")
            candidates = self._get_semantic_candidates(vendor_name, country, resolved_legal_name=resolved_legal_name, top_k=5)
        
        # If name search failed or no name, try email domain
        # NOTE: AI will semantically classify domains (corporate vs generic) in Supreme Judge step
        if not candidates and email_domain:
            print(f"🔎 Step 1B: Searching by email domain '{email_domain}'...")
            domain_candidates = self._get_candidates_by_domain(email_domain)
            if domain_candidates:
                print(f"✅ Found {len(domain_candidates)} candidates by domain")
                candidates.extend(domain_candidates)
            else:
                print(f"⚠️ No candidates found for domain '{email_domain}'")
        
        # If still no candidates and we have Tax ID or IBAN, could search by those
        # (Tax ID already checked in Step 0 for hard match, but could do fuzzy search here)
        
        if not candidates:
            print(f"⚠️ No candidates found via name ({vendor_name}), domain ({email_domain}), or other signals")
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
    
    def _get_semantic_candidates(self, vendor_name, country=None, resolved_legal_name=None, top_k=5):
        """
        Step 1: Use Vertex AI Search to find semantically similar vendors
        
        DUAL-NAME SEARCH: Tries both OCR name and Layer 3.5 resolved legal name
        
        Args:
            vendor_name: Vendor name to search for (original OCR name)
            country: Optional country filter
            resolved_legal_name: Optional resolved legal name from Layer 3.5 (e.g., "Artem Revva" for brand "Fully Booked")
            top_k: Maximum number of candidates to return
            
        Returns:
            List of candidate vendor dicts with metadata
        """
        if not vendor_name or vendor_name == "Unknown":
            return []
        
        # Build search query with original name
        search_query = f"Find vendor: {vendor_name}"
        if country:
            search_query += f" in {country}"
        
        print(f"🔎 Searching with original name: '{vendor_name}'")
        
        try:
            # Use Vertex Search service (search_vendor method)
            search_results = self.vertex_search.search_vendor(
                vendor_query=search_query,
                max_results=top_k
            )
            
            # CRITICAL FIX: Check if Vertex returned empty results
            # (could be no matches OR error was caught internally)
            if not search_results or len(search_results) == 0:
                print(f"⚠️ Vertex Search returned no results for original name '{vendor_name}'")
                
                # DUAL-NAME SEARCH: Try resolved legal name if available
                if resolved_legal_name and resolved_legal_name != vendor_name and resolved_legal_name != 'Unknown':
                    print(f"🔄 Retrying with resolved legal name: '{resolved_legal_name}'")
                    
                    # Build new search query with resolved legal name
                    resolved_search_query = f"Find vendor: {resolved_legal_name}"
                    if country:
                        resolved_search_query += f" in {country}"
                    
                    try:
                        search_results = self.vertex_search.search_vendor(
                            vendor_query=resolved_search_query,
                            max_results=top_k
                        )
                        
                        if search_results and len(search_results) > 0:
                            print(f"✅ Found {len(search_results)} candidates using resolved legal name")
                            # Continue with normal processing below
                        else:
                            print(f"⚠️ Vertex Search also returned no results for resolved name '{resolved_legal_name}'")
                            search_results = []
                    except Exception as resolved_search_error:
                        print(f"❌ Resolved name search error: {resolved_search_error}")
                        search_results = []
                
                # If still no results, trigger BigQuery fallback with BOTH names
                if not search_results or len(search_results) == 0:
                    print(f"🔄 Triggering BigQuery fallback...")
                    
                    # Try original name first
                    bigquery_results = self.bigquery.search_vendor_by_name(
                        vendor_name=vendor_name,
                        limit=top_k
                    )
                    
                    # Try resolved legal name if original returned nothing
                    if (not bigquery_results or len(bigquery_results) == 0) and resolved_legal_name and resolved_legal_name != vendor_name and resolved_legal_name != 'Unknown':
                        print(f"🔄 BigQuery fallback trying resolved legal name: '{resolved_legal_name}'")
                        bigquery_results = self.bigquery.search_vendor_by_name(
                            vendor_name=resolved_legal_name,
                            limit=top_k
                        )
                    
                    if not bigquery_results:
                        print(f"⚠️ BigQuery fallback returned no results for both names")
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
            # Try BOTH names in fallback
            try:
                # Try original name first
                bigquery_results = self.bigquery.search_vendor_by_name(
                    vendor_name=vendor_name,
                    limit=top_k
                )
                
                # Try resolved legal name if original returned nothing
                if (not bigquery_results or len(bigquery_results) == 0) and resolved_legal_name and resolved_legal_name != vendor_name and resolved_legal_name != 'Unknown':
                    print(f"🔄 BigQuery fallback trying resolved legal name: '{resolved_legal_name}'")
                    bigquery_results = self.bigquery.search_vendor_by_name(
                        vendor_name=resolved_legal_name,
                        limit=top_k
                    )
                
                if not bigquery_results:
                    print(f"⚠️ BigQuery fallback returned no results for both names")
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
    
    def _get_candidates_by_domain(self, email_domain):
        """
        Search BigQuery for vendors with matching email domain
        
        NOTE: No hardcoded domain filtering - AI Supreme Judge will semantically
        classify domains (CORPORATE_UNIQUE vs GENERIC_PROVIDER) in Step 2.
        
        Args:
            email_domain: Email domain to search for (e.g., 'aws.com', 'stripe.com', 'gmail.com')
            
        Returns:
            List of candidate vendor dicts with metadata
        """
        if not email_domain:
            return []
        
        # Clean domain (remove @ if present)
        clean_domain = email_domain.lstrip('@').lower()
        
        # BigQuery query to search for vendors with matching domain
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
        WHERE '{clean_domain}' IN UNNEST(domains)
        LIMIT 5
        """
        
        try:
            results = list(self.bigquery.client.query(query).result())
            
            if not results:
                return []
            
            print(f"✅ BigQuery domain search found {len(results)} vendors with domain '{clean_domain}'")
            
            # Convert BigQuery results to candidate format
            candidates = []
            for row in results:
                # Extract custom attributes
                custom_attrs = row.custom_attributes if hasattr(row, 'custom_attributes') else {}
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
                
                # Extract arrays (handle both list and None cases)
                emails = row.emails if hasattr(row, 'emails') and row.emails else []
                domains = row.domains if hasattr(row, 'domains') and row.domains else []
                countries = row.countries if hasattr(row, 'countries') and row.countries else []
                
                candidates.append({
                    "candidate_id": row.vendor_id,
                    "global_name": row.global_name if hasattr(row, 'global_name') else 'Unknown',
                    "normalized_name": row.normalized_name if hasattr(row, 'normalized_name') else '',
                    "aliases": [row.normalized_name] if hasattr(row, 'normalized_name') and row.normalized_name else [],
                    "tax_ids": tax_ids,
                    "domains": domains,
                    "emails": emails,
                    "addresses": addresses,
                    "countries": countries,
                    "custom_attributes": custom_attrs
                })
            
            return candidates
            
        except Exception as e:
            print(f"⚠️ Domain search failed (schema may be missing): {e}")
            return []  # Graceful fallback
    
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
        resolved_legal_name = invoice_data.get("resolved_legal_name", "")
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
        
        # Build the vendor name section with both names if available
        vendor_name_section = f'- **Invoice Header Name (OCR):** "{vendor_name}"'
        if resolved_legal_name and resolved_legal_name != 'Unknown' and resolved_legal_name != vendor_name:
            vendor_name_section += f'\n- **Resolved Legal Name (Layer 3.5 AI):** "{resolved_legal_name}"'
            vendor_name_section += '\n- **IMPORTANT:** This vendor has BOTH a brand/trade name AND a resolved legal entity name. The database may contain either name.'
        else:
            vendor_name_section = f'- **Vendor Name:** "{vendor_name}"'
        
        # 🧠 SEMANTIC VENDOR RESOLUTION ENGINE (Supreme Judge)
        # AI-First approach: Think like a human accountant, not a keyword matcher
        prompt = f"""
### SYSTEM IDENTITY
You are the **Global Entity Resolution Engine** — The Supreme Judge of Vendor Master Data.

Your mission: Determine if the **INVOICE VENDOR** and a **DATABASE CANDIDATE** represent the same real-world business entity.

You do NOT perform exact string matching. You perform **Semantic Identity Verification**.

### 📋 THE EVIDENCE
**<<< INVOICE VENDOR (THE UNKNOWN) >>>**
{vendor_name_section}
- **Tax ID:** "{tax_id}" (VAT/EIN/GST/GSTIN/CNPJ/HP)
- **Address:** "{address}"
- **Email Domain:** "{email_domain}" (e.g., @uber.com)
- **Phone:** "{phone}"
- **Bank Account Last 4:** "{bank_tail}"
- **Country:** "{country}"

**<<< DATABASE CANDIDATES (THE KNOWN) >>>**
{candidates_json}
{entity_classification_section}

### 🔍 ENTITY VALIDATION (CRITICAL FIRST STEP)
Before semantic matching, verify the invoice vendor is a legitimate business vendor.
If the entity is a **BANK**, **PAYMENT PROCESSOR**, or **GOVERNMENT ENTITY**, return verdict="INVALID_VENDOR".

**INVALID_VENDOR Response:**
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

### ⚖️ THE EVIDENCE HIERARCHY (HOW TO JUDGE)
Weigh evidence to calculate Match Confidence (0.0 - 1.0). Use semantic understanding, NOT keyword matching.

**EMAIL DOMAIN CLASSIFICATION (AI-First Semantic Analysis)**
CRITICAL: Analyze email domains using SEMANTIC INTELLIGENCE, not hardcoded keyword lists.

Classify email domains into these categories:

1. **CORPORATE_UNIQUE (Gold Tier, +45%)**: 
   - Domain matches or semantically relates to the company name
   - Examples: 
     * @acmecorp.com for "ACME Corporation"
     * @techservices.io for "Tech Services Ltd"
     * @vendor-business.co for "Vendor Business Inc"
   - Custom business domains that uniquely identify the vendor
   - High confidence evidence for matching

2. **GENERIC_PROVIDER (Bronze Tier, +0%)**:
   - Free email providers that ANYONE can use
   - Examples: gmail.com, yahoo.com, outlook.com, hotmail.com, icloud.com, live.com
   - Provides ZERO evidence for vendor matching
   - Individual freelancers or small businesses may use these

3. **RESELLER (Silver Tier, +20%)**:
   - Business email domain but may represent an intermediary or reseller
   - Domain doesn't match the invoice vendor name
   - Moderate confidence contribution

**IMPORTANT:** Use SEMANTIC UNDERSTANDING to classify domains. Do NOT use keyword matching!
- If domain semantically relates to vendor name → CORPORATE_UNIQUE
- If domain is a known email provider → GENERIC_PROVIDER  
- Otherwise → RESELLER

**🥇 GOLD TIER EVIDENCE (Definitive Proof → Confidence 0.95-1.0)**
1. **Tax ID Match:** VAT, EIN, GSTIN, or CNPJ matches exactly (or with minor formatting like dashes/spaces)
   - Example: "US-12-3456789" == "US123456789" → MATCH (1.0 confidence)
2. **IBAN/Bank Account Match:** Bank account numbers are identical
3. **CORPORATE_UNIQUE Domain Match:** Invoice email domain semantically matches vendor name
   - Invoice: billing@acmecorp.com + DB: support@acmecorp.com → Same domain, MATCH (0.95 confidence)
   - Invoice: invoices@vendor.io + DB: contact@vendor.io → Same domain, MATCH (0.95 confidence)

**🥈 SILVER TIER EVIDENCE (Strong Evidence → Confidence 0.75-0.90)**
1. **Semantic Name Match:** "Global Tech Services" == "GTS" == "Global Tech Inc."
   - Example: "TechCorp Ireland" == "TechCorp LLC" (geographic subsidiary)
   - Example: "OldBrand" == "NewBrand Holdings" (corporate rebrand)
2. **Address Proximity:** Same street address despite formatting differences
   - Example: "100 Main St" == "100 Main Street, Suite 400" → High confidence
   - Example: "Menlo Park, CA" matches "1 Hacker Way, Menlo Park" → Medium confidence
3. **Phone Number Match:** Same primary phone number (ignore country code formatting)

**🥉 BRONZE TIER EVIDENCE (Circumstantial → Confidence 0.50-0.70)**
1. **Generic Business Match:** "Consulting Services Inc" vs "Consulting Services Ltd"
   - Risky without additional evidence (address/domain/tax ID required)
2. **Partial Name Match:** "John Smith" vs "John Smith Design"
   - Low confidence without corroborating evidence

### 🧠 SEMANTIC REASONING RULES (AI-First, No Keywords)
Use these principles to think like a human accountant:

**1. CORPORATE HIERARCHY & ACQUISITIONS**
- If Invoice says "SubCo" and DB says "ParentCorp", check if ParentCorp acquired SubCo → MATCH (parent/child)
- If Invoice says "ProductBrand" and DB says "Holding Company" → MATCH (subsidiary relationship)
- Mark `is_subsidiary: true` and identify `parent_company_detected`

**2. BRAND vs. LEGAL ENTITY**
- Invoice: "Brand Name" → DB: "Legal Entity Corp" → MATCH (brand owned by legal entity)
- Invoice: "Product Brand" → DB: "Parent Corporation" → MATCH (brand/parent relationship)
- Invoice: "Service Name" → DB: "Operating Company LLC" → MATCH (product/parent relationship)

**3. GEOGRAPHIC SUBSIDIARIES**
- "VendorCo BV" (Netherlands) == "VendorCo Inc" (USA) → MATCH (global entity)
- "TechCorp Ireland" == "TechCorp Inc." → MATCH (tax subsidiary)
- "GlobalCo UK Ltd" == "GlobalCo Inc" → MATCH (regional entity)

**4. TYPOS & OCR ERRORS (AI-First Tolerance)**
- "Tech C0rp" == "Tech Corp" (OCR misread O as 0)
- "Buisness Services" == "Business Services" (typo)
- "Vend0r Inc" == "Vendor Inc" (OCR error)
- "C0mpany Ltd" == "Company Ltd" (OCR misread o as 0)

**5. MULTILINGUAL VENDOR NAMES**
- "חברת טכנולוגיה" (Hebrew) == "Technology Company Ltd" (English translation)
- "株式会社テクノロジー" (Japanese) == "Technology Corporation" (English)
- Use semantic understanding of translations, not exact matching

**6. THE "FALSE FRIEND" TRAP (Prevent Hallucinations)**
- "Phoenix Landscaping" ≠ "Phoenix Tech Inc." → Different industries, verify address/domain
- "Summit Airlines" ≠ "Summit Dental" → Different industries, same name
- "Global Express" (bank) ≠ "Global Express Delivery" (courier) → Validate entity type

**7. FRANCHISE & BRANCH LOGIC**
- "FranchiseCo (City Branch)" vs "FranchiseCo Corporation (HQ)"
  - If paying HQ → MATCH to HQ
  - If paying branch directly → MATCH to HQ unless DB has specific branch IDs

**8. DATA EVOLUTION (Self-Healing Database)**
- If MATCH found but invoice shows new information, flag for database updates:
  - New alias: DB has "OldCorp", Invoice says "NewCorp" → add_new_alias: "NewCorp"
  - New address: DB has "123 Old St", Invoice shows "123 New St" → add_new_address
  - New domain: DB has "@oldco.com", Invoice shows "@newco.com" → add_new_domain

### 📝 THE VERDICT SCHEMA (JSON ONLY)
{{
    "verdict": "MATCH" | "NEW_VENDOR" | "AMBIGUOUS",
    "match_details": {{
        "selected_vendor_id": "string (the 'candidate_id' field from the matching DB Candidate) or null",
        "confidence_score": 0.0-1.0,
        "match_reasoning": "Explain specifically: 'Matched via Tax ID', 'Matched via Corporate Domain + Fuzzy Name', etc.",
        "risk_analysis": "NONE | LOW | HIGH (e.g. 'Name matches but domain is gmail.com')",
        "evidence_breakdown": {{
            "email_domain": {{
                "domain_type": "CORPORATE_UNIQUE" | "GENERIC_PROVIDER" | "RESELLER" | "NOT_AVAILABLE",
                "tier": "GOLD" | "SILVER" | "BRONZE",
                "confidence_contribution": 0.0-50.0,
                "reasoning": "Explain why domain is classified this way (e.g., 'fully-booked.ca semantically matches company name Fully Booked')"
            }},
            "tax_id": {{
                "tier": "GOLD" | "SILVER" | "BRONZE",
                "matched": true|false,
                "confidence_contribution": 0.0-50.0,
                "reasoning": "Tax ID match status and reasoning"
            }},
            "name": {{
                "tier": "GOLD" | "SILVER" | "BRONZE",
                "matched": true|false,
                "confidence_contribution": 0.0-40.0,
                "reasoning": "Name match quality (exact, semantic, partial)"
            }},
            "address": {{
                "tier": "GOLD" | "SILVER" | "BRONZE",
                "matched": true|false,
                "confidence_contribution": 0.0-30.0,
                "reasoning": "Address match status"
            }},
            "phone": {{
                "tier": "GOLD" | "SILVER" | "BRONZE",
                "matched": true|false,
                "confidence_contribution": 0.0-15.0,
                "reasoning": "Phone match status"
            }}
        }}
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
6. **CRITICAL for MATCH verdict**: Copy the exact "candidate_id" value from the matching candidate and return it as "selected_vendor_id"
   Example: If matching candidate has "candidate_id": "AUTO_ARTEM_ANDREEVITCH_RE_27"
   Then you MUST return: "selected_vendor_id": "AUTO_ARTEM_ANDREEVITCH_RE_27"
"""
        
        try:
            # PRIMARY: OpenRouter Gemini 3 Pro, FALLBACK: gemini-2.5-flash
            response = self.gemini._generate_content_with_fallback(
                model=self.gemini.model_name,
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
            
            # Extract structured evidence breakdown (AI-First semantic classification)
            match_details = result.get("match_details", {})
            evidence_breakdown = match_details.get("evidence_breakdown")
            
            judge_result = {
                "verdict": raw_verdict,
                "vendor_id": match_details.get("selected_vendor_id"),
                "confidence": match_details.get("confidence_score", 0.0),
                "reasoning": match_details.get("match_reasoning", "No reasoning provided"),
                "risk_analysis": match_details.get("risk_analysis", "UNKNOWN"),
                "database_updates": result.get("database_updates", {}),
                "parent_child_logic": result.get("parent_child_logic", {
                    "is_subsidiary": False,
                    "parent_company_detected": None
                })
            }
            
            # Include structured evidence if AI provided it
            if evidence_breakdown:
                judge_result["evidence_breakdown"] = evidence_breakdown
                print("✅ Gemini returned structured evidence breakdown (AI-First semantic classification)")
            else:
                print("⚠️ Gemini did not return structured evidence - will use reasoning fallback")
            
            return judge_result
            
        except Exception as e:
            print(f"❌ Supreme Judge error: {e}")
            print(f"📝 Response text: {response.text[:500] if 'response' in locals() and hasattr(response, 'text') else 'No response'}")
            
            # Try regex fallback to extract verdict and reasoning
            fallback_result = self._fallback_parse_judge_response(response.text if 'response' in locals() and hasattr(response, 'text') else "")
            
            if fallback_result:
                print(f"✅ Fallback parsing succeeded: {fallback_result.get('verdict')}")
                return fallback_result
            
            # Final fallback: return NEW_VENDOR (safer than AMBIGUOUS for method mapping)
            return {
                "verdict": "NEW_VENDOR",
                "vendor_id": None,
                "confidence": 0.0,
                "reasoning": f"Error during Supreme Judge decision: {str(e)}. Unable to parse response.",
                "risk_analysis": "HIGH",
                "database_updates": {},
                "parent_child_logic": {
                    "is_subsidiary": False,
                    "parent_company_detected": None
                }
            }
    
    def _fallback_parse_judge_response(self, response_text):
        """
        Fallback parser using regex when JSON parsing fails.
        Attempts to extract verdict, vendor_id, confidence, and reasoning from malformed response.
        
        Args:
            response_text: The raw response text from Gemini
            
        Returns:
            dict or None if parsing fails completely
        """
        import re
        
        if not response_text:
            return None
            
        try:
            # Try to extract verdict using various patterns
            verdict_patterns = [
                r'"verdict"\s*:\s*"([^"]+)"',
                r'verdict["\']?\s*:\s*["\']?(\w+)',
                r'VERDICT\s*=\s*(\w+)',
            ]
            
            verdict = None
            for pattern in verdict_patterns:
                match = re.search(pattern, response_text, re.IGNORECASE)
                if match:
                    verdict = match.group(1).upper()
                    if verdict in ["MATCH", "NEW_VENDOR", "AMBIGUOUS"]:
                        break
                    verdict = None
            
            if not verdict:
                return None
            
            # Try to extract vendor_id
            vendor_id = None
            if verdict == "MATCH":
                vendor_id_patterns = [
                    r'"selected_vendor_id"\s*:\s*"([^"]+)"',
                    r'vendor_id["\']?\s*:\s*["\']?([^\s,}]+)',
                ]
                for pattern in vendor_id_patterns:
                    match = re.search(pattern, response_text)
                    if match and match.group(1) != "null":
                        vendor_id = match.group(1)
                        break
            
            # Try to extract confidence score
            confidence = 0.5  # Default
            confidence_patterns = [
                r'"confidence_score"\s*:\s*([0-9.]+)',
                r'confidence["\']?\s*:\s*([0-9.]+)',
            ]
            for pattern in confidence_patterns:
                match = re.search(pattern, response_text)
                if match:
                    try:
                        confidence = float(match.group(1))
                        confidence = min(max(confidence, 0.0), 1.0)  # Clamp to [0, 1]
                        break
                    except ValueError:
                        pass
            
            # Try to extract reasoning
            reasoning = "Fallback parsing - no detailed reasoning available"
            reasoning_patterns = [
                r'"match_reasoning"\s*:\s*"([^"]+)"',
                r'"reasoning"\s*:\s*"([^"]+)"',
                r'reasoning["\']?\s*:\s*["\']([^"\']+)',
            ]
            for pattern in reasoning_patterns:
                match = re.search(pattern, response_text)
                if match:
                    reasoning = match.group(1)
                    break
            
            print(f"📋 Fallback parsing results: verdict={verdict}, vendor_id={vendor_id}, confidence={confidence}")
            
            return {
                "verdict": verdict,
                "vendor_id": vendor_id,
                "confidence": confidence,
                "reasoning": reasoning,
                "risk_analysis": "MEDIUM",  # Default for fallback
                "database_updates": {},
                "parent_child_logic": {
                    "is_subsidiary": False,
                    "parent_company_detected": None
                }
            }
            
        except Exception as e:
            print(f"❌ Fallback parsing also failed: {e}")
            return None
    
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
