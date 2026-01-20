#!/usr/bin/env python3
import os
import json
import argparse
import time
import re
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

CHARTER_VIOLATIONS = [
    "Personal attacks or discriminatory remarks",
    "Spam or advertising",
    "Proposals unrelated to Audierne-Esquibien",
    "False information",
]

CHARTER_ENCOURAGED = [
    "Concrete and argued proposals",
    "Constructive criticism",
    "Questions and requests for clarification",
    "Sharing of experiences and expertise",
    "Suggestions for improvement",
]

CATEGORIES = [
    "economie",
    "logement",
    "culture",
    "ecologie",
    "associations",
    "jeunesse",
    "alimentation-bien-etre-soins",
]

@dataclass
class ValidationResult:
    is_valid: bool
    category: str
    original_category: str | None
    violations: list[str]
    encouraged_aspects: list[str]
    reasoning: str
    confidence: float
    
    def to_dict(self):
        return {
            "is_valid": self.is_valid,
            "category": self.category,
            "original_category": self.original_category,
            "violations": self.violations,
            "encouraged_aspects": self.encouraged_aspects,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
        }

class GeminiClient:
    def __init__(self, api_key: str | None = None):
        """
        Initialize Gemini client.

        Args:
            api_key: Optional API key override. Falls back to env vars.

        Raises:
            ValueError: If no API key is available.
            RuntimeError: If no compatible models are found.
        """
        import google.generativeai as genai
        key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GOOGLE_API_KEY not found")
        genai.configure(api_key=key)
        model_name = os.getenv("GEMINI_MODEL")
        if not model_name:
            try:
                models = genai.list_models()
                supported = [
                    m.name for m in models
                    if "generateContent" in getattr(m, "supported_generation_methods", [])
                ]
                if not supported:
                    raise RuntimeError("No Gemini models support generateContent")
                model_name = supported[0]
            except Exception as e:
                raise RuntimeError(f"Failed to list Gemini models: {e}")
        self.model = genai.GenerativeModel(model_name)
        self._last_call = 0.0

    def _throttle(self, min_interval=12.0):
        """
        Sleep between calls to respect rate limits.

        Args:
            min_interval: Minimum seconds between Gemini calls.
        """
        now = time.monotonic()
        wait = min_interval - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _generate(self, prompt: str):
        """
        Call Gemini with retries and rate-limit backoff.

        Args:
            prompt: Full prompt string.

        Returns:
            Gemini response object.

        Raises:
            RuntimeError: If retries are exhausted.
        """
        for _ in range(3):
            self._throttle()
            try:
                return self.model.generate_content(prompt)
            except Exception as e:
                msg = str(e)
                if "429" in msg and "retry" in msg:
                    m = re.search(r"retry in ([0-9.]+)s", msg)
                    time.sleep(float(m.group(1)) if m else 35)
                    continue
                raise
        raise RuntimeError("Gemini retries exhausted")

    def validate_and_classify_batch(self, items: list[dict]) -> list[dict]:
        """
        Validate charter compliance and classify categories for a batch.

        Args:
            items: List of dicts with keys: id, title, body, category.

        Returns:
            List of dicts with keys:
            id, is_valid, violations, encouraged_aspects, category, reasoning, confidence.
        """
        prompt = f"""You are validating citizen contributions in Audierne-Esquibien.

NOT ACCEPTED:
{chr(10).join(f"- {v}" for v in CHARTER_VIOLATIONS)}

ENCOURAGED:
{chr(10).join(f"- {e}" for e in CHARTER_ENCOURAGED)}

CATEGORIES: {', '.join(CATEGORIES)}

Return JSON ONLY:
{{"results":[{{"id":"","is_valid":true/false,"violations":[],"encouraged_aspects":[],"category":"","reasoning":"","confidence":0.0-1.0}}]}}

ITEMS:
{json.dumps(items, ensure_ascii=False)}
"""
        try:
            response = self._generate(prompt)
            cleaned = self._clean_json(response.text)
            data = json.loads(cleaned)
            return data.get("results", [])
        except Exception as e:
            return [
                {
                    "id": it.get("id"),
                    "is_valid": True,
                    "violations": [],
                    "encouraged_aspects": [],
                    "category": it.get("category") or CATEGORIES[0],
                    "reasoning": f"Error: {e}",
                    "confidence": 0.5,
                }
                for it in items
            ]
    
    def _clean_json(self, text: str) -> str:
        """
        Strip markdown fences and whitespace from LLM output.

        Args:
            text: Raw LLM response text.

        Returns:
            Cleaned JSON string.
        """
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()
    
    def validate_charter(self, title: str, body: str) -> dict:
        """
        Validate a single contribution against charter rules.

        Args:
            title: Issue title.
            body: Issue body.

        Returns:
            Dict with keys: is_valid, violations, encouraged_aspects, reasoning, confidence.
        """
        prompt = f"""Charter validator for Audierne-Esquibien.

NOT ACCEPTED:
{chr(10).join(f"- {v}" for v in CHARTER_VIOLATIONS)}

ENCOURAGED:
{chr(10).join(f"- {e}" for e in CHARTER_ENCOURAGED)}

TITLE: {title}
BODY: {body}

Return JSON only:
{{"is_valid": true/false, "violations": [], "encouraged_aspects": [], "reasoning": "", "confidence": 0.0-1.0}}"""
        
        try:
            response = self._generate(prompt)
            cleaned = self._clean_json(response.text)
            return json.loads(cleaned)
        except Exception as e:
            print(f"ERROR in validate_charter: {e}")
            print(f"Response: {response.text if 'response' in locals() else 'No response'}")
            return {"is_valid": True, "violations": [], "encouraged_aspects": [], "reasoning": f"Error: {e}", "confidence": 0.5}
    
    def classify_category(self, title: str, body: str, current_category: str | None = None) -> dict:
        """
        Classify a single contribution into one of the 7 categories.

        Args:
            title: Issue title.
            body: Issue body.
            current_category: Optional current category.

        Returns:
            Dict with keys: category, reasoning, confidence.
        """
        prompt = f"""Category classifier for Audierne-Esquibien.

CATEGORIES: {', '.join(CATEGORIES)}

economie: business, port, tourism | logement: housing | culture: heritage, events | ecologie: environment | associations: organizations | jeunesse: youth, schools | alimentation-bien-etre-soins: food, health

TITLE: {title}
BODY: {body}
{f"CURRENT: {current_category}" if current_category else ""}

Return JSON only:
{{"category": "one of 7 categories", "reasoning": "", "confidence": 0.0-1.0}}"""
        
        try:
            response = self._generate(prompt)
            cleaned = self._clean_json(response.text)
            result = json.loads(cleaned)
            if result["category"] not in CATEGORIES:
                result["category"] = CATEGORIES[0]
            return result
        except Exception as e:
            print(f"ERROR in classify_category: {e}")
            return {"category": current_category or CATEGORIES[0], "reasoning": f"Error: {e}", "confidence": 0.5}

class OpikTracer:
    def __init__(self, api_key: str | None = None, workspace: str | None = None):
        """
        Initialize Opik tracer; no-op if not configured.

        Args:
            api_key: Optional Opik API key override.
            workspace: Optional workspace override.
        """
        self.enabled = False
        try:
            import opik
            key = api_key or os.getenv("OPIK_API_KEY")
            if not key:
                return
            opik.configure(api_key=key, workspace=workspace or os.getenv("OPIK_WORKSPACE"))
            self.client = opik.Opik()
            self.enabled = True
        except:
            pass
    
    def trace_validation(self, issue_data: dict, validation_result: dict, category_result: dict):
        """
        Send a validation trace to Opik.

        Args:
            issue_data: Dict with title/body/category.
            validation_result: Dict with charter validation fields.
            category_result: Dict with category classification fields.
        """
        if not self.enabled:
            return
        try:
            self.client.trace(
                name="charter_validation",
                input={"title": issue_data["title"], "body": issue_data["body"], "original_category": issue_data.get("category")},
                output={"is_valid": validation_result["is_valid"], "violations": validation_result["violations"], 
                       "encouraged_aspects": validation_result["encouraged_aspects"], "category": category_result["category"]},
                metadata={"charter_confidence": validation_result["confidence"], "category_confidence": category_result["confidence"],
                         "charter_reasoning": validation_result["reasoning"], "category_reasoning": category_result["reasoning"]}
            )
        except:
            pass

def validate_issue(title: str, body: str, category: str | None = None, 
                   gemini_client: GeminiClient | None = None, opik_tracer: OpikTracer | None = None) -> ValidationResult:
    """
    Validate one issue and return a ValidationResult.

    Args:
        title: Issue title.
        body: Issue body.
        category: Optional input category.
        gemini_client: Optional Gemini client to reuse.
        opik_tracer: Optional Opik tracer to reuse.

    Returns:
        ValidationResult for the issue.
    """
    if gemini_client is None:
        gemini_client = GeminiClient()
    if opik_tracer is None:
        opik_tracer = OpikTracer()
    
    validation_result = gemini_client.validate_charter(title, body)
    category_result = gemini_client.classify_category(title, body, category)
    opik_tracer.trace_validation({"title": title, "body": body, "category": category}, validation_result, category_result)
    
    return ValidationResult(
        is_valid=validation_result["is_valid"],
        category=category_result["category"],
        original_category=category,
        violations=validation_result["violations"],
        encouraged_aspects=validation_result["encouraged_aspects"],
        reasoning=f"Charter: {validation_result['reasoning']} | Category: {category_result['reasoning']}",
        confidence=min(validation_result["confidence"], category_result["confidence"]),
    )

def main():
    """
    CLI entrypoint.

    Args:
        --title: Issue title.
        --body: Issue body.
        --category: Optional category.
        --json: Output JSON if set.
    """
    parser = argparse.ArgumentParser(description="Charter Validation Agent")
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--category")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    try:
        result = validate_issue(args.title, args.body, args.category)
        
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"\n{'='*60}\nVALIDATION RESULT\n{'='*60}")
            print(f"Valid: {result.is_valid}")
            if result.violations:
                print(f"Violations: {', '.join(result.violations)}")
            if result.encouraged_aspects:
                print(f"Encouraged: {', '.join(result.encouraged_aspects)}")
            print(f"Category: {result.category}" + (f" (was {result.original_category})" if result.original_category and result.original_category != result.category else ""))
            print(f"Reasoning: {result.reasoning}")
            print(f"Confidence: {result.confidence:.2f}\n{'='*60}\n")
        
        exit(0 if result.is_valid else 1)
    except Exception as e:
        print(f"Error: {e}")
        exit(2)

if __name__ == "__main__":
    main()