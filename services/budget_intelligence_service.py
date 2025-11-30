"""
Budget Intelligence Service - AI-Powered Spend Analytics & Forecasting

This service provides:
1. Crystal Ball Engine - BigQuery ML ARIMA_PLUS spend forecasting
2. Contract Watchdog - Vertex RAG-powered contract compliance auditing  
3. Auto-GL Categorizer - Gemini semantic GL classification
4. Zombie Hunter - Subscription churn and low-engagement detection
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from google.cloud import bigquery
from google.oauth2 import service_account
from config import config

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    types = None
    GENAI_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OpenAI = None
    OPENAI_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GL_CATEGORIES = [
    "Software",
    "Marketing", 
    "Office",
    "COGS",
    "Travel",
    "Legal",
    "Infrastructure",
    "Professional Services",
    "Subscriptions",
    "Utilities",
    "Other"
]


class BudgetIntelligenceService:
    """
    AI-Powered Budget Intelligence Service
    
    Features:
    - Crystal Ball Engine: BigQuery ML spend forecasting with ARIMA_PLUS
    - Contract Watchdog: RAG-powered contract compliance auditing
    - Auto-GL Categorizer: Semantic GL classification with Gemini
    - Zombie Hunter: Subscription churn detection
    """
    
    PROJECT_ID = "invoicereader-477008"
    DATASET_ID = "vendors_ai"
    
    def __init__(self):
        logger.info("🚀 Initializing Budget Intelligence Service...")
        
        self.bq_client = None
        self.openrouter_client = None
        self.gemini_client = None
        self.vertex_search = None
        
        self._init_bigquery()
        self._init_ai_clients()
        self._init_vertex_search()
        
        logger.info("✅ Budget Intelligence Service initialized")
    
    def _init_bigquery(self):
        """Initialize BigQuery client with service account credentials"""
        credentials = None
        
        sa_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON') or os.getenv('GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON')
        
        if sa_json:
            try:
                sa_info = json.loads(sa_json)
                credentials = service_account.Credentials.from_service_account_info(
                    sa_info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                logger.info("✅ BigQuery credentials loaded from environment")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse service account JSON: {e}")
        elif os.path.exists(config.VERTEX_RUNNER_SA_PATH):
            credentials = service_account.Credentials.from_service_account_file(
                config.VERTEX_RUNNER_SA_PATH,
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            logger.info("✅ BigQuery credentials loaded from file")
        
        if credentials:
            self.bq_client = bigquery.Client(
                credentials=credentials,
                project=self.PROJECT_ID
            )
        else:
            logger.warning("⚠️ No BigQuery credentials found, using default")
            self.bq_client = bigquery.Client(project=self.PROJECT_ID)
    
    def _init_ai_clients(self):
        """Initialize OpenRouter (primary) and Gemini (fallback) clients"""
        openrouter_api_key = os.getenv('OPENROUTERA')
        if openrouter_api_key and OPENAI_AVAILABLE:
            try:
                self.openrouter_client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=openrouter_api_key,
                    default_headers={
                        "HTTP-Referer": "https://replit.com",
                        "X-Title": "Budget Intelligence Service"
                    }
                )
                logger.info("✅ OpenRouter client initialized (PRIMARY)")
            except Exception as e:
                logger.warning(f"OpenRouter initialization failed: {e}")
        
        api_key = os.getenv('GOOGLE_GEMINI_API_KEY')
        if api_key and GENAI_AVAILABLE:
            try:
                self.gemini_client = genai.Client(api_key=api_key)
                logger.info("✅ Gemini client initialized (FALLBACK)")
            except Exception as e:
                logger.warning(f"Gemini initialization failed: {e}")
        
        if not self.openrouter_client and not self.gemini_client:
            logger.warning("⚠️ No AI client available - some features will be limited")
    
    def _init_vertex_search(self):
        """Initialize Vertex AI Search for contract RAG"""
        try:
            from services.vertex_search_service import VertexSearchService
            self.vertex_search = VertexSearchService()
            logger.info("✅ Vertex Search initialized for contract RAG")
        except Exception as e:
            logger.warning(f"Vertex Search initialization failed: {e}")
            self.vertex_search = None
    
    def _call_gemini(self, prompt: str, response_format: str = "json") -> Optional[str]:
        """
        Call Gemini API with OpenRouter primary, native fallback
        
        Args:
            prompt: The prompt to send
            response_format: "json" or "text"
            
        Returns:
            Response text or None on failure
        """
        if self.openrouter_client:
            try:
                kwargs = {
                    "model": "google/gemini-2.0-flash-001",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1
                }
                if response_format == "json":
                    kwargs["response_format"] = {"type": "json_object"}
                
                response = self.openrouter_client.chat.completions.create(**kwargs)
                return response.choices[0].message.content
            except Exception as e:
                logger.warning(f"OpenRouter call failed: {e}")
        
        if self.gemini_client and GENAI_AVAILABLE:
            try:
                config_obj = {
                    "temperature": 0.1
                }
                if response_format == "json":
                    config_obj["response_mime_type"] = "application/json"
                
                response = self.gemini_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config=config_obj
                )
                return response.text
            except Exception as e:
                logger.warning(f"Gemini native call failed: {e}")
        
        return None
    
    def initialize_forecast_models(self) -> Dict[str, Any]:
        """
        Create/update ARIMA_PLUS time-series model in BigQuery for spend forecasting
        
        This creates a model that learns from historical invoice data to predict
        future spend patterns per vendor.
        
        Returns:
            Dict with status and model info
        """
        model_id = f"{self.PROJECT_ID}.{self.DATASET_ID}.spend_forecast_model"
        
        check_data_query = f"""
        SELECT COUNT(*) as row_count,
               COUNT(DISTINCT vendor_name) as vendor_count,
               MIN(invoice_date) as earliest_date,
               MAX(invoice_date) as latest_date
        FROM `{self.PROJECT_ID}.{self.DATASET_ID}.invoices`
        WHERE invoice_date IS NOT NULL AND amount IS NOT NULL
        """
        
        try:
            result = self.bq_client.query(check_data_query).result()
            data_stats = list(result)[0]
            
            if data_stats.row_count < 10:
                return {
                    "status": "insufficient_data",
                    "message": f"Need at least 10 invoices with dates, found {data_stats.row_count}",
                    "row_count": data_stats.row_count,
                    "vendor_count": data_stats.vendor_count
                }
            
            logger.info(f"📊 Found {data_stats.row_count} invoices from {data_stats.vendor_count} vendors")
            
        except Exception as e:
            logger.warning(f"Could not check invoice data: {e}")
            return {
                "status": "error",
                "message": f"Failed to check invoice data: {str(e)}"
            }
        
        create_model_query = f"""
        CREATE OR REPLACE MODEL `{model_id}`
        OPTIONS(
            model_type='ARIMA_PLUS',
            time_series_timestamp_col='invoice_month',
            time_series_data_col='monthly_spend',
            time_series_id_col='vendor_name',
            auto_arima=TRUE,
            data_frequency='MONTHLY',
            holiday_region='US'
        ) AS
        SELECT
            vendor_name,
            DATE_TRUNC(invoice_date, MONTH) as invoice_month,
            SUM(amount) as monthly_spend
        FROM `{self.PROJECT_ID}.{self.DATASET_ID}.invoices`
        WHERE invoice_date IS NOT NULL 
          AND amount IS NOT NULL
          AND vendor_name IS NOT NULL
        GROUP BY vendor_name, DATE_TRUNC(invoice_date, MONTH)
        HAVING monthly_spend > 0
        ORDER BY vendor_name, invoice_month
        """
        
        try:
            logger.info("🔨 Creating/updating ARIMA_PLUS forecast model...")
            job = self.bq_client.query(create_model_query)
            job.result()
            
            logger.info("✅ Forecast model created successfully")
            return {
                "status": "success",
                "model_id": model_id,
                "message": "ARIMA_PLUS model created/updated successfully",
                "data_stats": {
                    "row_count": data_stats.row_count,
                    "vendor_count": data_stats.vendor_count,
                    "date_range": f"{data_stats.earliest_date} to {data_stats.latest_date}"
                }
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to create forecast model: {error_msg}")
            return {
                "status": "error",
                "message": f"Failed to create model: {error_msg}"
            }
    
    def get_vendor_forecast(self, vendor_name: str, months: int = 3) -> Dict[str, Any]:
        """
        Get predicted spend for next N months for a specific vendor using ML.FORECAST
        
        Args:
            vendor_name: Name of the vendor to forecast
            months: Number of months to forecast (default 3)
            
        Returns:
            Dict with forecast data or error info
        """
        model_id = f"{self.PROJECT_ID}.{self.DATASET_ID}.spend_forecast_model"
        
        forecast_query = f"""
        SELECT
            vendor_name,
            forecast_timestamp,
            forecast_value as predicted_spend,
            prediction_interval_lower_bound as lower_bound,
            prediction_interval_upper_bound as upper_bound,
            confidence_level
        FROM ML.FORECAST(
            MODEL `{model_id}`,
            STRUCT({months} AS horizon, 0.95 AS confidence_level)
        )
        WHERE vendor_name = @vendor_name
        ORDER BY forecast_timestamp
        """
        
        try:
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("vendor_name", "STRING", vendor_name)
                ]
            )
            
            result = self.bq_client.query(forecast_query, job_config=job_config).result()
            forecasts = []
            
            for row in result:
                forecasts.append({
                    "month": row.forecast_timestamp.strftime("%Y-%m") if row.forecast_timestamp else None,
                    "predicted_spend": float(row.predicted_spend) if row.predicted_spend else 0,
                    "lower_bound": float(row.lower_bound) if row.lower_bound else 0,
                    "upper_bound": float(row.upper_bound) if row.upper_bound else 0,
                    "confidence": float(row.confidence_level) if row.confidence_level else 0.95
                })
            
            if not forecasts:
                return {
                    "status": "no_data",
                    "vendor_name": vendor_name,
                    "message": f"No forecast data available for vendor '{vendor_name}'"
                }
            
            total_predicted = sum(f["predicted_spend"] for f in forecasts)
            
            return {
                "status": "success",
                "vendor_name": vendor_name,
                "months_forecasted": months,
                "forecasts": forecasts,
                "total_predicted_spend": total_predicted,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            error_msg = str(e)
            
            if "Not found" in error_msg or "does not exist" in error_msg.lower():
                return {
                    "status": "model_not_found",
                    "vendor_name": vendor_name,
                    "message": "Forecast model not initialized. Run initialize_forecast_models() first."
                }
            
            logger.error(f"Forecast query failed: {error_msg}")
            return {
                "status": "error",
                "vendor_name": vendor_name,
                "message": f"Forecast failed: {error_msg}"
            }
    
    def get_all_forecasts(self, months: int = 3, limit: int = 50) -> Dict[str, Any]:
        """
        Get forecasts for all vendors
        
        Args:
            months: Number of months to forecast (default 3)
            limit: Maximum number of vendors to include (default 50)
            
        Returns:
            Dict with forecasts for all vendors
        """
        model_id = f"{self.PROJECT_ID}.{self.DATASET_ID}.spend_forecast_model"
        
        forecast_query = f"""
        WITH forecasts AS (
            SELECT
                vendor_name,
                forecast_timestamp,
                forecast_value as predicted_spend,
                prediction_interval_lower_bound as lower_bound,
                prediction_interval_upper_bound as upper_bound
            FROM ML.FORECAST(
                MODEL `{model_id}`,
                STRUCT({months} AS horizon, 0.95 AS confidence_level)
            )
        ),
        vendor_totals AS (
            SELECT 
                vendor_name,
                SUM(predicted_spend) as total_predicted,
                COUNT(*) as months_count
            FROM forecasts
            GROUP BY vendor_name
            ORDER BY total_predicted DESC
            LIMIT {limit}
        )
        SELECT 
            f.vendor_name,
            f.forecast_timestamp,
            f.predicted_spend,
            f.lower_bound,
            f.upper_bound,
            vt.total_predicted
        FROM forecasts f
        JOIN vendor_totals vt ON f.vendor_name = vt.vendor_name
        ORDER BY vt.total_predicted DESC, f.vendor_name, f.forecast_timestamp
        """
        
        try:
            result = self.bq_client.query(forecast_query).result()
            
            vendors = {}
            for row in result:
                vendor = row.vendor_name
                if vendor not in vendors:
                    vendors[vendor] = {
                        "vendor_name": vendor,
                        "total_predicted": float(row.total_predicted) if row.total_predicted else 0,
                        "forecasts": []
                    }
                
                vendors[vendor]["forecasts"].append({
                    "month": row.forecast_timestamp.strftime("%Y-%m") if row.forecast_timestamp else None,
                    "predicted_spend": float(row.predicted_spend) if row.predicted_spend else 0,
                    "lower_bound": float(row.lower_bound) if row.lower_bound else 0,
                    "upper_bound": float(row.upper_bound) if row.upper_bound else 0
                })
            
            vendor_list = sorted(vendors.values(), key=lambda x: x["total_predicted"], reverse=True)
            grand_total = sum(v["total_predicted"] for v in vendor_list)
            
            return {
                "status": "success",
                "months_forecasted": months,
                "vendor_count": len(vendor_list),
                "grand_total_predicted": grand_total,
                "vendors": vendor_list,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            error_msg = str(e)
            
            if "Not found" in error_msg or "does not exist" in error_msg.lower():
                return {
                    "status": "model_not_found",
                    "message": "Forecast model not initialized. Run initialize_forecast_models() first."
                }
            
            logger.error(f"All forecasts query failed: {error_msg}")
            return {
                "status": "error",
                "message": f"Forecast failed: {error_msg}"
            }
    
    def detect_anomalies(self, threshold: float = 0.05) -> Dict[str, Any]:
        """
        Run ML.DETECT_ANOMALIES to find invoices deviating from normal patterns
        
        Args:
            threshold: Anomaly threshold (lower = more sensitive, default 0.05)
            
        Returns:
            Dict with detected anomalies
        """
        model_id = f"{self.PROJECT_ID}.{self.DATASET_ID}.spend_forecast_model"
        
        anomaly_query = f"""
        WITH monthly_spend AS (
            SELECT
                vendor_name,
                DATE_TRUNC(invoice_date, MONTH) as invoice_month,
                SUM(amount) as monthly_spend
            FROM `{self.PROJECT_ID}.{self.DATASET_ID}.invoices`
            WHERE invoice_date IS NOT NULL 
              AND amount IS NOT NULL
              AND vendor_name IS NOT NULL
            GROUP BY vendor_name, DATE_TRUNC(invoice_date, MONTH)
        )
        SELECT *
        FROM ML.DETECT_ANOMALIES(
            MODEL `{model_id}`,
            STRUCT({threshold} AS anomaly_prob_threshold),
            (SELECT * FROM monthly_spend)
        )
        WHERE is_anomaly = TRUE
        ORDER BY anomaly_probability DESC
        LIMIT 100
        """
        
        try:
            result = self.bq_client.query(anomaly_query).result()
            
            anomalies = []
            for row in result:
                anomalies.append({
                    "vendor_name": row.vendor_name,
                    "month": row.invoice_month.strftime("%Y-%m") if hasattr(row, 'invoice_month') and row.invoice_month else None,
                    "actual_spend": float(row.monthly_spend) if hasattr(row, 'monthly_spend') else 0,
                    "expected_lower": float(row.lower_bound) if hasattr(row, 'lower_bound') else None,
                    "expected_upper": float(row.upper_bound) if hasattr(row, 'upper_bound') else None,
                    "anomaly_probability": float(row.anomaly_probability) if hasattr(row, 'anomaly_probability') else 1.0,
                    "severity": "HIGH" if row.anomaly_probability > 0.9 else "MEDIUM" if row.anomaly_probability > 0.7 else "LOW"
                })
            
            return {
                "status": "success",
                "anomaly_count": len(anomalies),
                "threshold": threshold,
                "anomalies": anomalies,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            error_msg = str(e)
            
            if "Not found" in error_msg or "does not exist" in error_msg.lower():
                return {
                    "status": "model_not_found",
                    "message": "Forecast model not initialized. Run initialize_forecast_models() first."
                }
            
            logger.error(f"Anomaly detection failed: {error_msg}")
            return {
                "status": "error",
                "message": f"Anomaly detection failed: {error_msg}"
            }
    
    def get_burn_rate(self) -> Dict[str, Any]:
        """
        Calculate current month spend vs forecasted end-of-month
        
        Returns:
            Dict with burn rate analysis
        """
        current_date = datetime.now()
        month_start = current_date.replace(day=1)
        days_in_month = (month_start.replace(month=month_start.month % 12 + 1, day=1) - timedelta(days=1)).day if month_start.month < 12 else 31
        days_elapsed = current_date.day
        
        current_spend_query = f"""
        SELECT 
            COALESCE(SUM(amount), 0) as current_spend,
            COUNT(*) as invoice_count,
            COUNT(DISTINCT vendor_name) as vendor_count
        FROM `{self.PROJECT_ID}.{self.DATASET_ID}.invoices`
        WHERE invoice_date >= DATE_TRUNC(CURRENT_DATE(), MONTH)
          AND invoice_date <= CURRENT_DATE()
        """
        
        try:
            result = self.bq_client.query(current_spend_query).result()
            current_data = list(result)[0]
            
            current_spend = float(current_data.current_spend) if current_data.current_spend else 0
            
            if days_elapsed > 0:
                daily_rate = current_spend / days_elapsed
                projected_eom = daily_rate * days_in_month
            else:
                daily_rate = 0
                projected_eom = 0
            
            forecast_result = self.get_all_forecasts(months=1, limit=100)
            
            ml_forecast = 0
            if forecast_result.get("status") == "success":
                ml_forecast = forecast_result.get("grand_total_predicted", 0)
            
            if ml_forecast > 0:
                variance = projected_eom - ml_forecast
                variance_pct = (variance / ml_forecast) * 100
            else:
                variance = 0
                variance_pct = 0
            
            if variance_pct > 20:
                status = "OVER_BUDGET"
                alert = "⚠️ Projected to exceed forecast by >20%"
            elif variance_pct > 10:
                status = "WARNING"
                alert = "📊 Trending above forecast"
            elif variance_pct < -20:
                status = "UNDER_BUDGET"
                alert = "📉 Significantly under forecast"
            else:
                status = "ON_TRACK"
                alert = "✅ Spending on track"
            
            return {
                "status": "success",
                "month": current_date.strftime("%Y-%m"),
                "days_elapsed": days_elapsed,
                "days_in_month": days_in_month,
                "current_spend": current_spend,
                "invoice_count": current_data.invoice_count,
                "vendor_count": current_data.vendor_count,
                "daily_burn_rate": daily_rate,
                "projected_eom_spend": projected_eom,
                "ml_forecasted_spend": ml_forecast,
                "variance": variance,
                "variance_percent": variance_pct,
                "budget_status": status,
                "alert": alert,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Burn rate calculation failed: {e}")
            return {
                "status": "error",
                "message": f"Burn rate calculation failed: {str(e)}"
            }
    
    def audit_invoice_against_contract(self, vendor_name: str, invoice_amount: float) -> Dict[str, Any]:
        """
        Audit invoice against contract using Vertex RAG and Gemini
        
        This searches for vendor MSA/contract documents, extracts pricing caps,
        and compares the invoice amount against contract terms.
        
        Args:
            vendor_name: Name of the vendor
            invoice_amount: Invoice amount to check
            
        Returns:
            Dict with verdict: SAFE, WARNING, or OVERCHARGE_ALERT
        """
        if not self.vertex_search:
            return {
                "status": "error",
                "verdict": "UNKNOWN",
                "message": "Vertex Search not available for contract lookup"
            }
        
        try:
            contract_results = self.vertex_search.search_vendor(
                f"{vendor_name} contract MSA pricing terms agreement",
                max_results=5
            )
            
            if not contract_results:
                return {
                    "status": "no_contract",
                    "verdict": "UNKNOWN",
                    "vendor_name": vendor_name,
                    "invoice_amount": invoice_amount,
                    "message": f"No contract documents found for vendor '{vendor_name}'"
                }
            
            contract_context = self.vertex_search.format_context(contract_results)
            
            prompt = f"""🔍 CONTRACT COMPLIANCE AUDITOR

You are auditing an invoice against contract terms.

## VENDOR: {vendor_name}
## INVOICE AMOUNT: ${invoice_amount:,.2f}

## CONTRACT DOCUMENTS FOUND:
{contract_context}

## YOUR TASK:
1. Extract any pricing caps, rate limits, or maximum amounts from the contracts
2. Compare the invoice amount against these limits
3. Provide a verdict

## OUTPUT (JSON):
{{
    "pricing_cap_found": true|false,
    "cap_amount": float or null,
    "cap_type": "monthly_max|per_unit|annual_max|project_cap" or null,
    "invoice_vs_cap_percent": float or null (invoice as % of cap),
    "verdict": "SAFE|WARNING|OVERCHARGE_ALERT",
    "reasoning": "Detailed explanation of your analysis",
    "contract_excerpts": ["Relevant contract text snippets"]
}}

VERDICT RULES:
- SAFE: Invoice is within contract limits (< 90% of cap)
- WARNING: Invoice is close to limit (90-100% of cap)  
- OVERCHARGE_ALERT: Invoice exceeds contract limits (> 100% of cap)
- If no pricing cap found, return UNKNOWN with explanation
"""
            
            response_text = self._call_gemini(prompt, response_format="json")
            
            if not response_text:
                return {
                    "status": "ai_error",
                    "verdict": "UNKNOWN",
                    "vendor_name": vendor_name,
                    "invoice_amount": invoice_amount,
                    "message": "AI analysis failed"
                }
            
            try:
                if '```json' in response_text:
                    response_text = response_text.split('```json')[1].split('```')[0]
                elif '```' in response_text:
                    response_text = response_text.split('```')[1].split('```')[0]
                
                analysis = json.loads(response_text.strip())
            except json.JSONDecodeError:
                analysis = {
                    "verdict": "UNKNOWN",
                    "reasoning": response_text
                }
            
            return {
                "status": "success",
                "vendor_name": vendor_name,
                "invoice_amount": invoice_amount,
                "verdict": analysis.get("verdict", "UNKNOWN"),
                "pricing_cap_found": analysis.get("pricing_cap_found", False),
                "cap_amount": analysis.get("cap_amount"),
                "cap_type": analysis.get("cap_type"),
                "invoice_vs_cap_percent": analysis.get("invoice_vs_cap_percent"),
                "reasoning": analysis.get("reasoning", ""),
                "contract_excerpts": analysis.get("contract_excerpts", []),
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Contract audit failed: {e}")
            return {
                "status": "error",
                "verdict": "UNKNOWN",
                "vendor_name": vendor_name,
                "invoice_amount": invoice_amount,
                "message": f"Contract audit failed: {str(e)}"
            }
    
    def categorize_spend(self, line_items: List[Dict[str, Any]], update_bigquery: bool = False) -> Dict[str, Any]:
        """
        Use Gemini to classify line items into GL categories
        
        Categories: Software, Marketing, Office, COGS, Travel, Legal, 
                   Infrastructure, Professional Services, Subscriptions, Utilities, Other
        
        Args:
            line_items: List of line items with 'description', 'amount', 'invoice_id'
            update_bigquery: If True, update the invoices table with GL categories
            
        Returns:
            Dict with categorized items
        """
        if not line_items:
            return {
                "status": "no_items",
                "message": "No line items provided"
            }
        
        items_for_prompt = []
        for i, item in enumerate(line_items):
            items_for_prompt.append({
                "index": i,
                "description": item.get("description", ""),
                "amount": item.get("amount", 0),
                "vendor": item.get("vendor_name", "")
            })
        
        prompt = f"""🏷️ GL CATEGORIZER - Classify expenses into accounting categories

## LINE ITEMS TO CATEGORIZE:
{json.dumps(items_for_prompt, indent=2)}

## VALID GL CATEGORIES:
1. Software - SaaS subscriptions, software licenses, app purchases
2. Marketing - Advertising, promotion, brand, content, social media
3. Office - Supplies, furniture, equipment, facilities
4. COGS - Cost of goods sold, direct production costs, inventory
5. Travel - Transportation, hotels, meals during travel
6. Legal - Legal services, compliance, contracts, IP
7. Infrastructure - Cloud, hosting, servers, networking, IT ops
8. Professional Services - Consulting, freelancers, contractors
9. Subscriptions - Recurring services (non-software)
10. Utilities - Electricity, internet, phone, water
11. Other - Uncategorized expenses

## OUTPUT (JSON array):
[
  {{
    "index": 0,
    "gl_category": "Software",
    "confidence": 0.95,
    "reasoning": "Description mentions SaaS subscription"
  }}
]

Categorize ALL {len(items_for_prompt)} items. Be accurate based on description and vendor context.
"""
        
        response_text = self._call_gemini(prompt, response_format="json")
        
        if not response_text:
            for item in line_items:
                item["gl_category"] = "Other"
                item["gl_confidence"] = 0.0
                item["gl_reasoning"] = "AI categorization failed"
            
            return {
                "status": "ai_error",
                "message": "AI categorization failed, defaulting to 'Other'",
                "categorized_items": line_items
            }
        
        try:
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0]
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0]
            
            categorizations = json.loads(response_text.strip())
            
            if isinstance(categorizations, dict):
                categorizations = categorizations.get("items", categorizations.get("results", []))
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse categorization response: {e}")
            for item in line_items:
                item["gl_category"] = "Other"
                item["gl_confidence"] = 0.0
                item["gl_reasoning"] = "JSON parse failed"
            
            return {
                "status": "parse_error",
                "message": "Failed to parse AI response",
                "categorized_items": line_items
            }
        
        cat_map = {c.get("index", i): c for i, c in enumerate(categorizations)}
        
        for i, item in enumerate(line_items):
            cat = cat_map.get(i, {})
            item["gl_category"] = cat.get("gl_category", "Other")
            item["gl_confidence"] = cat.get("confidence", 0.5)
            item["gl_reasoning"] = cat.get("reasoning", "")
            
            if item["gl_category"] not in GL_CATEGORIES:
                item["gl_category"] = "Other"
        
        if update_bigquery:
            self._update_invoice_gl_categories(line_items)
        
        category_summary = {}
        for item in line_items:
            cat = item["gl_category"]
            if cat not in category_summary:
                category_summary[cat] = {"count": 0, "total_amount": 0}
            category_summary[cat]["count"] += 1
            category_summary[cat]["total_amount"] += item.get("amount", 0)
        
        return {
            "status": "success",
            "items_categorized": len(line_items),
            "category_summary": category_summary,
            "categorized_items": line_items,
            "generated_at": datetime.now().isoformat()
        }
    
    def _update_invoice_gl_categories(self, categorized_items: List[Dict[str, Any]]) -> bool:
        """Update BigQuery invoices table with GL categories"""
        try:
            ensure_column_query = f"""
            ALTER TABLE `{self.PROJECT_ID}.{self.DATASET_ID}.invoices`
            ADD COLUMN IF NOT EXISTS gl_category STRING
            """
            
            try:
                self.bq_client.query(ensure_column_query).result()
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Could not add gl_category column: {e}")
            
            for item in categorized_items:
                invoice_id = item.get("invoice_id")
                gl_category = item.get("gl_category", "Other")
                
                if invoice_id:
                    update_query = f"""
                    UPDATE `{self.PROJECT_ID}.{self.DATASET_ID}.invoices`
                    SET gl_category = @gl_category
                    WHERE invoice_id = @invoice_id
                    """
                    
                    job_config = bigquery.QueryJobConfig(
                        query_parameters=[
                            bigquery.ScalarQueryParameter("gl_category", "STRING", gl_category),
                            bigquery.ScalarQueryParameter("invoice_id", "STRING", invoice_id)
                        ]
                    )
                    
                    self.bq_client.query(update_query, job_config=job_config).result()
            
            logger.info(f"✅ Updated GL categories for {len(categorized_items)} items")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update GL categories in BigQuery: {e}")
            return False
    
    def get_zombie_subscriptions(self, inactive_days: int = 60) -> Dict[str, Any]:
        """
        Find subscriptions with low engagement or cancellation signals
        
        Zombies are subscriptions where:
        - No invoices in the last N days (inactive_days)
        - Had regular invoices before (at least 2 historical invoices)
        - Sudden stop in billing pattern
        
        Args:
            inactive_days: Days of inactivity to flag as zombie (default 60)
            
        Returns:
            Dict with zombie subscription analysis
        """
        zombie_query = f"""
        WITH vendor_activity AS (
            SELECT 
                vendor_name,
                COUNT(*) as total_invoices,
                MAX(invoice_date) as last_invoice_date,
                MIN(invoice_date) as first_invoice_date,
                AVG(amount) as avg_amount,
                SUM(amount) as total_spend,
                DATE_DIFF(MAX(invoice_date), MIN(invoice_date), DAY) as activity_span_days,
                COUNT(*) / NULLIF(DATE_DIFF(MAX(invoice_date), MIN(invoice_date), MONTH), 0) as invoices_per_month
            FROM `{self.PROJECT_ID}.{self.DATASET_ID}.invoices`
            WHERE vendor_name IS NOT NULL
              AND invoice_date IS NOT NULL
            GROUP BY vendor_name
            HAVING COUNT(*) >= 2
        )
        SELECT 
            vendor_name,
            total_invoices,
            last_invoice_date,
            first_invoice_date,
            avg_amount,
            total_spend,
            activity_span_days,
            invoices_per_month,
            DATE_DIFF(CURRENT_DATE(), last_invoice_date, DAY) as days_since_last_invoice
        FROM vendor_activity
        WHERE DATE_DIFF(CURRENT_DATE(), last_invoice_date, DAY) > {inactive_days}
          AND activity_span_days > 30
          AND invoices_per_month > 0.3
        ORDER BY total_spend DESC
        LIMIT 50
        """
        
        try:
            result = self.bq_client.query(zombie_query).result()
            
            zombies = []
            for row in result:
                days_inactive = row.days_since_last_invoice
                
                if days_inactive > 180:
                    severity = "DEAD"
                    recommendation = "Likely cancelled - remove from tracking"
                elif days_inactive > 120:
                    severity = "CRITICAL"
                    recommendation = "Contact vendor to confirm status"
                elif days_inactive > 90:
                    severity = "HIGH"
                    recommendation = "Check if still needed, consider cancellation"
                else:
                    severity = "MEDIUM"
                    recommendation = "Monitor - may be paused or irregular billing"
                
                zombies.append({
                    "vendor_name": row.vendor_name,
                    "total_invoices": row.total_invoices,
                    "last_invoice_date": row.last_invoice_date.isoformat() if row.last_invoice_date else None,
                    "days_since_last_invoice": days_inactive,
                    "avg_amount": float(row.avg_amount) if row.avg_amount else 0,
                    "total_spend": float(row.total_spend) if row.total_spend else 0,
                    "invoices_per_month": float(row.invoices_per_month) if row.invoices_per_month else 0,
                    "severity": severity,
                    "recommendation": recommendation
                })
            
            total_zombie_spend = sum(z["total_spend"] for z in zombies)
            avg_monthly_zombie = sum(z["avg_amount"] * z["invoices_per_month"] for z in zombies)
            
            return {
                "status": "success",
                "zombie_count": len(zombies),
                "inactive_threshold_days": inactive_days,
                "total_historical_spend": total_zombie_spend,
                "estimated_monthly_zombie_cost": avg_monthly_zombie,
                "zombies": zombies,
                "severity_breakdown": {
                    "DEAD": len([z for z in zombies if z["severity"] == "DEAD"]),
                    "CRITICAL": len([z for z in zombies if z["severity"] == "CRITICAL"]),
                    "HIGH": len([z for z in zombies if z["severity"] == "HIGH"]),
                    "MEDIUM": len([z for z in zombies if z["severity"] == "MEDIUM"])
                },
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Zombie detection failed: {e}")
            return {
                "status": "error",
                "message": f"Zombie detection failed: {str(e)}"
            }
    
    def get_budget_summary(self) -> Dict[str, Any]:
        """
        Get a comprehensive budget intelligence summary
        
        Returns:
            Dict with complete budget analysis including forecasts, anomalies, and zombies
        """
        logger.info("📊 Generating comprehensive budget summary...")
        
        summary = {
            "generated_at": datetime.now().isoformat(),
            "burn_rate": None,
            "forecasts": None,
            "anomalies": None,
            "zombies": None
        }
        
        try:
            summary["burn_rate"] = self.get_burn_rate()
        except Exception as e:
            summary["burn_rate"] = {"status": "error", "message": str(e)}
        
        try:
            summary["forecasts"] = self.get_all_forecasts(months=3, limit=10)
        except Exception as e:
            summary["forecasts"] = {"status": "error", "message": str(e)}
        
        try:
            summary["anomalies"] = self.detect_anomalies(threshold=0.1)
        except Exception as e:
            summary["anomalies"] = {"status": "error", "message": str(e)}
        
        try:
            summary["zombies"] = self.get_zombie_subscriptions(inactive_days=60)
        except Exception as e:
            summary["zombies"] = {"status": "error", "message": str(e)}
        
        summary["status"] = "success"
        return summary
