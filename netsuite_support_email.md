# NetSuite Integration Critical Issue - Vendor Search API Failing

**To:** Igor (NetSuite Support)  
**Subject:** URGENT: REST API Vendor Search Consistently Failing - Need SuiteQL Access or Alternative Solution  
**Account:** 11236545_SB1 (Sandbox)  
**Date:** November 24, 2025  

## Executive Summary

We have successfully created vendors in NetSuite via REST API, but cannot search for them to link invoices. The REST API search endpoint (`/record/v1/vendor?q=...`) consistently returns "Invalid search query" errors despite following documentation and multiple fix attempts.

## Critical Blocker

**Invoice creation is completely blocked** because we cannot find existing vendors to link them. This affects our entire accounts payable automation workflow.

## Specific Example Case

### Vendor Details
- **Vendor Name:** Artem Andreevitch Revva  
- **Vendor ID (Our System):** V2149  
- **NetSuite Internal ID:** 490 (confirmed exists in NetSuite UI)  
- **Email:** admin@fully-booked.ca  
- **Tax ID:** Not provided in invoice data  

### Invoice Unable to Process
- **Invoice Number:** 0000212  
- **Amount:** $67.25  
- **Cannot be created** because vendor search fails  

## Detailed Technical Timeline

### 1. VENDOR CREATION ATTEMPT (09:25:34 UTC)

**Request:**
```http
POST https://11236545-sb1.suitetalk.api.netsuite.com/services/rest/record/v1/vendor
Content-Type: application/json

{
  "companyName": "Artem Andreevitch Revva",
  "email": "admin@fully-booked.ca",
  "externalId": "vendor:V2149",
  "isPerson": true,
  "firstName": "Artem Andreevitch",
  "lastName": "Revva"
}
```

**Response (400 Bad Request):**
```json
{
  "type": "https://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.4.1",
  "title": "Bad Request",
  "status": 400,
  "o:errorDetails": [{
    "detail": "Error while accessing a resource. This entity already exists.",
    "o:errorCode": "USER_ERROR"
  }]
}
```

**✅ This confirms vendor EXISTS in NetSuite**

### 2. VENDOR SEARCH ATTEMPTS (Multiple Failed Approaches)

#### Attempt 1: Search by Company Name
**Request:**
```http
GET https://11236545-sb1.suitetalk.api.netsuite.com/services/rest/record/v1/vendor?q=companyName CONTAIN 'Artem Andreevitch Revva'
```

**OAuth Signature Base String (showing encoding issue):**
```
GET&https%3A%2F%2F11236545-sb1.suitetalk.api.netsuite.com%2Fservices%2Frest%2Frecord%2Fv1%2Fvendor&
q%3DcompanyName%2520CONTAIN%2520%2527Artem%2520Andreevitch%2520Revva%2527
```
**NOTE:** Double encoding visible - `%2520` instead of `%20`

**Response (400 Bad Request):**
```json
{
  "type": "https://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.4.1",
  "title": "Bad Request",
  "status": 400,
  "o:errorDetails": [{
    "detail": "Invalid search query. Provide a valid search query.",
    "o:errorQueryParam": "q",
    "o:errorCode": "INVALID_PARAMETER"
  }]
}
```

#### Attempt 2: Search by Email
**Request:**
```http
GET https://11236545-sb1.suitetalk.api.netsuite.com/services/rest/record/v1/vendor?q=email IS 'admin@fully-booked.ca'
```

**Response:** Same 400 "Invalid search query" error

#### Attempt 3: Search by External ID
**Request:**
```http
GET https://11236545-sb1.suitetalk.api.netsuite.com/services/rest/record/v1/vendor?q=externalId IS 'vendor:V2149'
```

**Response:** Same 400 "Invalid search query" error

## Technical Issues Identified

### 1. Double Encoding Problem
The OAuth 1.0a signature generation is causing double URL encoding:
- First encoding: `companyName CONTAIN 'Artem'` → `companyName%20CONTAIN%20%27Artem%27`
- Second encoding in signature: `%20` → `%2520`
- NetSuite receives: `companyName%2520CONTAIN%2520%27Artem%2527`

### 2. Query Syntax Issues
We've tried multiple syntaxes per documentation:
- `CONTAIN` (singular) as per API docs
- `IS` operator for exact match
- With and without quotes around values

All consistently fail with "Invalid search query"

### 3. Missing Data Challenge
Invoice data often lacks:
- Tax ID/VAT numbers
- Valid email addresses
- Other indexed fields

This forces us to search by company name, which appears unsupported by the REST API.

## Code Implementation Details

### OAuth Signature Generation (Python)
```python
def _generate_oauth_signature(self, method: str, url: str, oauth_params: Dict, 
                             query_params: Dict = None) -> str:
    all_params = oauth_params.copy()
    if query_params:
        all_params.update(query_params)
    
    sorted_params = sorted(all_params.items())
    
    # Using quote() for RFC 5849 compliance
    encoded_params = []
    for key, value in sorted_params:
        encoded_key = quote(str(key), safe='~-._')
        encoded_value = quote(str(value), safe='~-._')
        encoded_params.append(f"{encoded_key}={encoded_value}")
    
    param_string = '&'.join(encoded_params)
    signature_base = f"{method.upper()}&{quote(url, safe='')}&{quote(param_string, safe='')}"
    
    signing_key = f"{consumer_secret}&{token_secret}"
    signature_bytes = hmac.new(
        signing_key.encode('utf-8'),
        signature_base.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    return base64.b64encode(signature_bytes).decode('utf-8')
```

## Attempted Fixes

1. ✅ Changed `CONTAINS` to `CONTAIN` (singular) per NetSuite docs
2. ✅ Fixed OAuth encoding from `quote_plus()` to `quote()` with `safe='~-._'`
3. ✅ Removed double encoding in request builder
4. ✅ Implemented prioritized search (Tax ID → Email → Name)
5. ❌ All REST API searches still fail

## What We Need From NetSuite Support

### Option 1: Enable SuiteQL (Preferred)
We understand SuiteQL would allow us to query:
```sql
SELECT id FROM vendor WHERE externalid = 'vendor:V2149'
```
**Question:** How do we enable SuiteQL access for account 11236545_SB1?

### Option 2: Fix REST API Search
**Questions:**
1. What is the exact, working syntax for REST API vendor search with spaces/special characters?
2. Is there a way to search by externalId that actually works?
3. Why does `companyName CONTAIN 'name'` fail when documentation suggests it should work?

### Option 3: Alternative Approach
1. Can we extract the internal ID from the "entity already exists" error response?
2. Is there a different endpoint for vendor lookup we should use?
3. Should we use SOAP/SuiteTalk instead of REST?

## Environment Details

- **NetSuite Account:** 11236545_SB1 (Sandbox)
- **API Version:** REST Record API v1
- **OAuth:** 1.0a with HMAC-SHA256
- **Integration Platform:** Python 3.11
- **OAuth Library:** Custom implementation per RFC 5849

## Full Request/Response Logs

### Successful API Call (For Comparison)
```
GET /services/rest/record/v1/metadata-catalog/
Response: 200 OK (Returns catalog successfully)
```

### Failed Vendor Search (Full Headers)
```
GET /services/rest/record/v1/vendor?q=companyName%20CONTAIN%20'Artem%20Andreevitch%20Revva'
Authorization: OAuth realm="11236545_SB1", 
  oauth_consumer_key="e162be22ea020cb163efbe4686cba8fe7e38dc9f25fbfdbe3d27cb3b0fe5e50d",
  oauth_nonce="85824670251",
  oauth_signature="[signature]",
  oauth_signature_method="HMAC-SHA256",
  oauth_timestamp="1763977124",
  oauth_token="172f2aad9a02f16ea3498387efe404e09860788249dc6c3f802f91e82f1522e1",
  oauth_version="1.0"

Response: 400 Bad Request
{
  "status": 400,
  "o:errorDetails": [{
    "detail": "Invalid search query. Provide a valid search query.",
    "o:errorQueryParam": "q",
    "o:errorCode": "INVALID_PARAMETER"
  }]
}
```

## Business Impact

- **Blocked Invoices:** 50+ invoices waiting to be synced
- **Manual Work Required:** Currently having to manually create invoices in NetSuite
- **Automation Broken:** Our entire AP automation workflow is non-functional

## Urgent Request

We need either:
1. **Instructions to enable SuiteQL** for our account
2. **Working example of REST API vendor search** with special characters/spaces
3. **Alternative method** to reliably find vendors by external ID

This is blocking our production deployment. Any guidance would be greatly appreciated.

## Contact Information

**Your Company:** [Your Company Name]  
**Technical Contact:** [Your Name]  
**Email:** [Your Email]  
**Phone:** [Your Phone]  
**Timezone:** [Your Timezone]  

Thank you for your urgent attention to this matter.

---

## Attachments

1. Full OAuth signature generation code (netsuite_service.py)
2. Complete request/response logs for failed searches
3. Screenshot of vendor existing in NetSuite UI (Internal ID: 490)
4. Invoice data that cannot be processed

## Additional Notes for Igor

We've spent significant development time trying to resolve this. The vendor clearly exists (confirmed by both the "entity already exists" error and manual UI verification), but we cannot programmatically find it via REST API to link invoices.

The core issue appears to be that NetSuite's REST API search doesn't support the query syntax documented, particularly when dealing with:
- Spaces in search values
- Special characters (quotes, apostrophes)
- Non-ASCII characters

We believe SuiteQL is the correct solution but need guidance on enabling it for our sandbox account.