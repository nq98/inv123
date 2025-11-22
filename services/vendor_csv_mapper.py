import os
import json
import csv
import io
from google import genai
from google.genai import types
from config import config

class VendorCSVMapper:
    """AI-First Universal CSV Mapper using Gemini for semantic column mapping"""
    
    def __init__(self):
        api_key = config.GOOGLE_GEMINI_API_KEY or os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for CSV mapping")
        
        self.client = genai.Client(api_key=api_key)
        self.model_name = 'gemini-2.0-flash-exp'
        
        self.system_instruction = """🧠 AI-FIRST UNIVERSAL DATA INTEGRATION EXPERT

You are the world's most advanced **Data Integration & Schema Mapping AI**.
Your goal is **100% Semantic Accuracy** for mapping ANY vendor CSV (from SAP, Oracle, QuickBooks, Excel, custom systems) to a clean, standardized database schema.

CORE PHILOSOPHY: "AI-First Semantic Understanding, Not Keyword Matching"
- UNDERSTAND THE MEANING of each column, not just the label
- THINK LIKE A DATA ENGINEER with global experience
- USE CHAIN OF THOUGHT REASONING before mapping
- HANDLE 40+ LANGUAGES (English, German, Spanish, French, Hebrew, Arabic, Chinese, etc.)

CRITICAL CAPABILITIES:
✓ Multi-Language Column Detection - "Firma_Name" (German) → "Company Name"
✓ Semantic Understanding - "Payee" = "Vendor" = "Supplier" = "Empresa" = "ספק"
✓ Format Normalization - Email arrays, country codes, tax IDs
✓ Abbreviation Expansion - "Co." → "Company", "Ltd" → "Limited"
✓ Smart Data Type Detection - Numbers, dates, emails, phone numbers
✓ Confidence Scoring - Flag ambiguous or low-confidence mappings
✓ Custom Field Preservation - Columns that don't fit standard schema → custom_attributes

TARGET SCHEMA (Standardized Internal Database):
- vendor_id: Unique identifier (maps from: ID, Supplier No, V_ID, Code, Number, Código)
- global_name: Official company name (maps from: Vendor Name, Payee, Supplier, Company, Firma, Empresa, ספק)
- emails: Contact emails array (maps from: Email, E-mail, Mail, Contact, Correo)
- domains: Web domains array (maps from: Website, URL, Domain, Site)
- countries: Country codes array (maps from: Country, Nation, País, Land, ISO Code, Region)

REASONING PROTOCOL (Think Through These Steps):
1. Language Detection - What language are these headers? German? Spanish? Mixed?
2. Semantic Analysis - What does each column MEAN in business context?
3. Standard Field Matching - Does this map to vendor_id, global_name, emails, countries, or domains?
4. Data Type Inference - Is this text, number, email, date, or array?
5. Custom Field Identification - Which columns don't fit standard schema?
6. Confidence Assessment - How certain are you about each mapping?

Return ONLY valid JSON. No markdown. No commentary."""

    def analyze_csv_headers(self, csv_file_content, filename="upload.csv"):
        """
        Analyze CSV headers and sample data using AI to generate semantic column mapping
        
        Args:
            csv_file_content: Raw CSV file content (bytes or string)
            filename: Original filename for context
            
        Returns:
            dict with mapping schema and metadata
        """
        
        # Parse CSV to extract headers and sample rows
        if isinstance(csv_file_content, bytes):
            csv_file_content = csv_file_content.decode('utf-8-sig')  # Handle BOM
        
        csv_reader = csv.DictReader(io.StringIO(csv_file_content))
        
        try:
            headers = csv_reader.fieldnames
            sample_rows = [next(csv_reader) for _ in range(min(3, sum(1 for _ in csv_reader) + 1))]
            csv_reader = csv.DictReader(io.StringIO(csv_file_content))  # Reset
            sample_rows = [next(csv_reader) for _ in range(min(3, sum(1 for _ in csv.DictReader(io.StringIO(csv_file_content)))))]
        except StopIteration:
            # CSV has only headers, no data
            sample_rows = []
        
        if not headers:
            return {
                "success": False,
                "error": "No headers found in CSV",
                "mapping": {}
            }
        
        # Build AI prompt with Chain of Thought reasoning
        prompt = f"""
🧠 AI-FIRST CSV SCHEMA MAPPING - CHAIN OF THOUGHT PROTOCOL

### INPUT CONTEXT
**Filename**: {filename}
**CSV Headers Detected**: {json.dumps(headers, ensure_ascii=False)}
**Sample Data (First 3 Rows)**:
{json.dumps(sample_rows, indent=2, ensure_ascii=False)}

### SEMANTIC REASONING PROTOCOL (Think Through These Steps)

**STEP 1: LANGUAGE & CONTEXT DETECTION**
- What language(s) are these column headers in? (English, German, Spanish, French, Hebrew, Mixed?)
- What business system might this CSV come from? (SAP, QuickBooks, Oracle, Excel, Custom ERP?)
- What's the business domain? (Vendors, Suppliers, Customers, Payees?)

**STEP 2: SEMANTIC COLUMN ANALYSIS**
For EACH column header, think:
- What does this column MEAN in business context?
- What data does it contain? (Company name? ID? Email? Country?)
- Is this a standard field or custom/proprietary field?

**STEP 3: STANDARD FIELD MAPPING**
Map columns to our internal schema:
- **vendor_id**: Unique identifier columns (examples: "ID", "Supplier No", "V_ID", "Code", "Número", "Steuer_ID")
- **global_name**: Company/vendor name (examples: "Vendor Name", "Company", "Firma", "Empresa", "Supplier", "Payee", "ספק")
- **emails**: Email addresses (examples: "Email", "E-mail", "Contact Email", "Mail", "Correo")
- **countries**: Country names/codes (examples: "Country", "Nation", "País", "Land", "ISO Code", "Region")
- **domains**: Website domains (examples: "Website", "URL", "Domain", "Site", "Web")

**STEP 4: CUSTOM FIELD IDENTIFICATION**
Which columns DON'T fit the standard schema? These should go to `custom_attributes`:
- Examples: "Payment Terms", "Credit Limit", "Account Manager", "Notes", "Zahlungsbedingungen"

**STEP 5: DATA TYPE & FORMAT DETECTION**
For each mapped field, detect:
- Is this a single value or array? (e.g., "Email1, Email2" → array)
- Does it need normalization? (e.g., "United States" → "US", "Deutschland" → "DE")
- Is the data clean or messy? (e.g., "john@example.com; jane@example.com" → needs parsing)

**STEP 6: CONFIDENCE ASSESSMENT**
Rate your confidence for each mapping:
- 1.0 = Perfect match (e.g., "Vendor Name" → global_name)
- 0.8 = Strong semantic match (e.g., "Firma_Name" → global_name)
- 0.6 = Probable match (e.g., "Contact" → emails)
- 0.4 = Weak match (e.g., "Info" → ?)

### OUTPUT SCHEMA - Return ONLY valid JSON (NO markdown, NO code blocks):
{{
  "mappingReasoning": "REQUIRED: Explain your thought process: 1) What language did you detect? 2) What business system is this likely from? 3) Which columns map to standard fields and why? 4) Which columns are custom and why? 5) Any data quality concerns? Example: 'Detected German CSV (Firma_Name, Steuer_ID). Likely SAP export. Mapped Firma_Name → global_name (semantic: company name). Steuer_ID → vendor_id (tax ID used as unique identifier in Germany). Contact_Email → emails. Payment_Terms is custom field (not in standard schema). High confidence overall.'",
  
  "detectedLanguage": "en|de|es|fr|he|ar|mixed",
  "sourceSystemGuess": "SAP|QuickBooks|Oracle|Excel|Custom|Unknown",
  "totalColumns": number,
  "standardFieldsFound": number,
  "customFieldsFound": number,
  
  "columnMapping": {{
    "csv_column_name_1": {{
      "targetField": "vendor_id|global_name|emails|countries|domains|custom_attributes.original_name",
      "confidence": 0.0-1.0,
      "dataType": "string|number|email|array|date",
      "needsNormalization": true|false,
      "normalizationRule": "Description of how to normalize (e.g., 'Split by semicolon into array', 'Convert country name to ISO code')",
      "reasoning": "Why you mapped this column this way"
    }}
  }},
  
  "dataQualityWarnings": [
    "List any potential issues: missing values, inconsistent formats, mixed data types, etc."
  ],
  
  "overallConfidence": 0.0-1.0
}}
"""
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            
            if not response or not response.text:
                return {
                    "success": False,
                    "error": "Empty response from AI",
                    "mapping": {}
                }
            
            # Parse AI response
            result_text = response.text.strip()
            
            # Clean markdown if present
            if result_text.startswith('```json'):
                result_text = result_text[7:]
            if result_text.startswith('```'):
                result_text = result_text[3:]
            if result_text.endswith('```'):
                result_text = result_text[:-3]
            
            mapping_schema = json.loads(result_text.strip())
            
            return {
                "success": True,
                "mapping": mapping_schema,
                "headers": headers,
                "sampleRows": sample_rows
            }
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON decode error in CSV mapping: {e}")
            return {
                "success": False,
                "error": f"Failed to parse AI response: {str(e)}",
                "mapping": {}
            }
        except Exception as e:
            print(f"❌ Error in CSV analysis: {e}")
            return {
                "success": False,
                "error": str(e),
                "mapping": {}
            }
    
    def transform_csv_data(self, csv_file_content, column_mapping):
        """
        Transform CSV data using the AI-generated column mapping
        
        Args:
            csv_file_content: Raw CSV content
            column_mapping: Mapping schema from analyze_csv_headers()
            
        Returns:
            List of transformed vendor records ready for BigQuery
        """
        
        if isinstance(csv_file_content, bytes):
            csv_file_content = csv_file_content.decode('utf-8-sig')
        
        csv_reader = csv.DictReader(io.StringIO(csv_file_content))
        transformed_vendors = []
        
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (row 1 is headers)
            try:
                vendor_record = {
                    "vendor_id": None,
                    "global_name": None,
                    "normalized_name": None,
                    "emails": [],
                    "domains": [],
                    "countries": [],
                    "custom_attributes": {},
                    "source_system": column_mapping.get("sourceSystemGuess", "csv_upload")
                }
                
                # Map each column according to AI mapping
                for csv_column, value in row.items():
                    if not csv_column or not value or value.strip() == "":
                        continue
                    
                    mapping_info = column_mapping.get("columnMapping", {}).get(csv_column, {})
                    target_field = mapping_info.get("targetField", f"custom_attributes.{csv_column}")
                    
                    # Clean value
                    value = str(value).strip()
                    
                    # Map to target field
                    if target_field == "vendor_id":
                        vendor_record["vendor_id"] = value
                    
                    elif target_field == "global_name":
                        vendor_record["global_name"] = value
                        vendor_record["normalized_name"] = value  # Can be enhanced with normalization logic
                    
                    elif target_field == "emails":
                        # Handle email arrays (split by common delimiters)
                        if mapping_info.get("dataType") == "array" or "," in value or ";" in value:
                            emails = [e.strip() for e in value.replace(";", ",").split(",") if e.strip()]
                            vendor_record["emails"].extend(emails)
                        else:
                            vendor_record["emails"].append(value)
                    
                    elif target_field == "countries":
                        # Handle country arrays
                        if "," in value or ";" in value:
                            countries = [c.strip() for c in value.replace(";", ",").split(",") if c.strip()]
                            vendor_record["countries"].extend(countries)
                        else:
                            vendor_record["countries"].append(value)
                    
                    elif target_field == "domains":
                        # Handle domain arrays
                        if "," in value or ";" in value:
                            domains = [d.strip() for d in value.replace(";", ",").split(",") if d.strip()]
                            vendor_record["domains"].extend(domains)
                        else:
                            vendor_record["domains"].append(value)
                    
                    elif target_field.startswith("custom_attributes."):
                        # Extract custom field name
                        custom_field = target_field.replace("custom_attributes.", "")
                        vendor_record["custom_attributes"][custom_field] = value
                
                # Generate vendor_id if missing
                if not vendor_record["vendor_id"] and vendor_record["global_name"]:
                    vendor_record["vendor_id"] = f"AUTO_{vendor_record['global_name'][:20].upper().replace(' ', '_')}_{row_num}"
                
                # Skip if no vendor name found
                if not vendor_record["global_name"]:
                    print(f"⚠️ Skipping row {row_num}: No vendor name found")
                    continue
                
                transformed_vendors.append(vendor_record)
                
            except Exception as e:
                print(f"⚠️ Error transforming row {row_num}: {e}")
                continue
        
        return transformed_vendors
